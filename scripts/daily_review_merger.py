#!/usr/bin/env python3
"""
财联社午评/收评/焦点复盘 采集 → 入库 → 输出摘要
用法: python3 daily_review_merger.py <午评|收评|焦点复盘>
"""
import sqlite3, subprocess, re, os, sys, json
from datetime import datetime, timezone, timedelta

TZ_CST = timezone(timedelta(hours=8))
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "daily_market.db")

SUBJECT_MAP = {
    "午评":    "1140",
    "收评":    "1139",
    "焦点复盘": "1135",
}

def curl_html(url: str) -> str:
    cmd = [
        "curl", "-s", "-L", url,
        "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "-H", "Accept-Language: zh-CN,zh;q=0.9",
        "-H", "Accept: text/html,application/xhtml+xml",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.stdout
    except Exception as e:
        print(f"[ERROR] curl失败: {e}")
        return ""

def parse_article_content(html: str) -> dict:
    """从文章HTML中提取标题+正文段落列表"""
    m = re.search(r'<title>([^<]+)</title>', html)
    title = m.group(1).replace('_财联社', '').strip() if m else ''
    paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
    lines = []
    for p in paras:
        text = re.sub(r'<[^>]+>', '', p).strip()
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        if len(text) > 10:
            lines.append(text)
    content = '\n'.join(lines[:50])
    return {"title": title, "content": content}

def parse_article_date(html: str) -> str:
    """从文章页提取日期 YYYY-MM-DD"""
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', html)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""

def extract_key_points(content: str) -> dict:
    """
    五维结构化提炼 v2：基于段落主题句 + 内容段落匹配
    策略：
    1. 识别每段的主题类别（看开头关键词）
    2. 内容充实段落按类别收集
    3. 去重 + 长度过滤
    """
    lines = [ln.strip() for ln in content.split('\n') if len(ln.strip()) > 15]
    
    # 主题词定义（优先级从高到低）
    # 格式: (类别, [主题关键词])
    CATEGORIES = [
        ("market_summary", ["市场全天", "市场早盘", "市场震荡", "市场低开", "指数早盘", "指数全天", "沪指", "深成指", "创业板指", "科创", "三大指数", "今日市场", "整体来看", "总体来看", "盘面来看", "回顾今日", "截至收盘", "全天市场", "午后市场"]),
        ("sector_hot",     ["板块", "概念", "行业", "涨停潮", "涨停股", "领涨", "走强", "活跃", "爆发", "轮动", "涨价", "景气", "需求", "供给", "工业气体", "氦气", "算力", "煤炭", "医药", "半导体", "AI", "算力租赁"]),
        ("opportunities",  ["可关注", "机会", "留意", "强势", "新高", "看好", "重点", "资金流入", "资金追捧", "连板", "晋级", "涨停", "突破", "资金回流", "回暖", "催化", "景气延续", "二次涨价", "业绩预增"]),
        ("risks",          ["注意", "风险", "谨慎", "回避", "高位", "获利盘", "暴雷", "破位", "补跌", "松动", "分化", "挤压", "证伪", "压力", "回调", "业绩不及", "亏损", "跌停", "炸板", "失守", "业绩变脸"]),
        ("outlook",        ["后市", "短期", "中期", "认为", "表示", "指出", "分析", "预期", "研判", "情绪", "修复", "企稳", "节后", "五一", "假期", "回流", "出金", "真空期", "热点扩散", "轮动"]),
    ]
    
    def category_score(line: str) -> tuple:
        """返回 (类别, 匹配分数)
        评分规则：
        - 以主题词开头：+2
        - 内容中含主题词：+1
        - 总分>=1才收录（宽松兜底）
        """
        best_cat, best_score = "market_summary", 0
        for cat, keywords in CATEGORIES:
            score = 0
            for k in keywords:
                if line.startswith(k):
                    score += 2
                elif k in line:
                    score += 1
            if score > best_score:
                best_score = score
                best_cat = cat
        return best_cat, best_score

    sections = {k: [] for k in ("market_summary", "sector_hot", "opportunities", "risks", "outlook")}

    for line in lines:
        cat, score = category_score(line)
        if score >= 1:  # 至少1个关键词命中就收录
            # 去重：检查是否已收录相同或包含文本
            dup = any(
                line in existing or existing in line
                for items in sections.values()
                for existing in items
            )
            if not dup and 15 < len(line) < 350:
                sections[cat].append(line)

    # ── 内容补全逻辑（当关键维度为空时）────────────────────
    # 如果 sector_hot 为空但内容涉及板块，从 market_summary 提取
    if not sections["sector_hot"] and sections["market_summary"]:
        for line in sections["market_summary"]:
            # 提取含板块关键词的句子作为热点
            for kw in ["板块", "概念", "氦气", "算力", "绿电", "CCL", "煤炭", "医药"]:
                if kw in line and line not in sections["sector_hot"]:
                    sections["sector_hot"].append(line)
                    break

    # 如果 opportunities/risks/outlook 为空，从其他段落匹配
    for line in lines:
        for cat, kw_list in [
            ("opportunities", ["机会", "留意", "强势", "新高", "连板", "晋级", "催化"]),
            ("risks", ["风险", "高位", "回调", "分化", "暴雷", "跌超", "炸板"]),
            ("outlook", ["后市", "短期", "五一", "节后", "情绪", "修复", "企稳"]),
        ]:
            if not sections[cat] and any(k in line for k in kw_list):
                dup = any(
                    line in existing or existing in line
                    for items in sections.values()
                    for existing in items
                )
                if not dup:
                    sections[cat].append(line)

    # 汇总：每类取最多n条
    def lim(items, n=5):
        seen, result = set(), []
        for x in items:
            key = x[:20]  # 按前20字去重
            if key not in seen:
                seen.add(key); result.append(x)
        return result[:n]

    ms = lim(sections["market_summary"], 2)
    sh = lim(sections["sector_hot"], 4)
    opp = lim(sections["opportunities"], 3)
    risk = lim(sections["risks"], 3)
    outlook = lim(sections["outlook"], 3)

    return {
        "market_summary": "\n".join(ms),
        "sector_hot":     "\n".join(sh),
        "opportunities":  "\n".join(opp),
        "risks":          "\n".join(risk),
        "outlook":        "\n".join(outlook),
        "raw_points":     "\n".join(ms + sh + opp + risk + outlook),
    }

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            review_type TEXT NOT NULL CHECK(review_type IN ('午评','收评','焦点复盘')),
            title TEXT,
            content TEXT,
            key_points TEXT,
            report_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, review_type)
        )
    """)
    conn.commit()
    conn.close()

def save_review(trade_date: str, review_type: str, title: str, content: str, key_points: dict):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    kp_json = json.dumps(key_points, ensure_ascii=False)
    c.execute("""
        INSERT OR REPLACE INTO daily_review
        (trade_date, review_type, title, content, key_points, report_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (trade_date, review_type, title, content, kp_json, content))
    conn.commit()
    conn.close()

def fetch_and_save(review_type: str, trade_date: str) -> dict:
    subject_id = SUBJECT_MAP.get(review_type)
    if not subject_id:
        print(f"[ERROR] 未知类型: {review_type}")
        return None

    html = curl_html(f"https://www.cls.cn/subject/{subject_id}")
    article_ids = re.findall(r'/detail/(\d+)', html)
    if not article_ids:
        print(f"[WARN] 未找到{review_type}文章ID")
        return None

    article_id = article_ids[0]
    article_html = curl_html(f"https://www.cls.cn/detail/{article_id}")
    article_date = parse_article_date(article_html)
    if article_date and article_date != trade_date:
        print(f"[SKIP] {review_type}非今日({article_date})，跳过")
        return None

    data = parse_article_content(article_html)
    kp = extract_key_points(data["content"])
    save_review(trade_date, review_type, data["title"], data["content"], kp)
    return {"title": data["title"], "content": data["content"], "key_points": kp}

def print_report(review_type: str, result: dict):
    kp = result["key_points"]
    width = 52
    print(f"\n{'='*width}")
    print(f"【{review_type}】{result['title']}")
    print(f"{'='*width}")

    def show(label, text, prefix=""):
        if not text: return
        print(f"\n【{label}】")
        for line in text.split('\n'):
            if line.strip(): print(f"  {prefix}{line.strip()}")

    show("市场概况", kp.get("market_summary",""))
    show("热点板块", kp.get("sector_hot",""))
    show("机会提示", kp.get("opportunities",""), "💡 ")
    show("风险提示", kp.get("risks",""), "⚠️ ")
    show("后市研判", kp.get("outlook",""), "📋 ")
    print(f"\n{'='*width}")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 daily_review_merger.py <午评|收评|焦点复盘>")
        sys.exit(1)

    review_type = sys.argv[1]
    now = datetime.now(TZ_CST)
    trade_date = now.strftime("%Y-%m-%d")

    if now.weekday() >= 5:
        print(f"[SKIP] 周末({now.strftime('%A')})跳过")
        sys.exit(0)

    result = fetch_and_save(review_type, trade_date)
    if result:
        print_report(review_type, result)
    else:
        print(f"[WARN] 未获取到{review_type}数据")

if __name__ == "__main__":
    main()
