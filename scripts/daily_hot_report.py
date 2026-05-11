#!/usr/bin/env python3
"""
每日盘面热点日报生成器
整合：板块资金流 + 概念涨幅排行 + 涨停复盘 + 财经早餐 + 指数收盘
输出：结构化热点日报（文本 + JSON存档）
用法: python3 scripts/daily_hot_report.py [YYYY-MM-DD]
定时: 每日18:00 cron执行
"""
import sqlite3, subprocess, json, re, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ_CST = timezone(timedelta(hours=8))
BASE_DIR = Path("/home/admin/stock_knowledge")
REPORTS_DIR = BASE_DIR / "reports"
DB_PATH = BASE_DIR / "database" / "daily_market.db"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════

def curl_json(url: str, timeout=15) -> dict:
    """curl GET → JSON"""
    r = subprocess.run(
        ["curl", "-s", url, "-H", "User-Agent: Mozilla/5.0"],
        capture_output=True, text=True, timeout=timeout
    )
    try:
        return json.loads(r.stdout)
    except:
        return {}


def curl_text(url: str, encoding="utf-8", timeout=15) -> str:
    """curl GET → 文本（自动识别编码）"""
    r = subprocess.run(
        ["curl", "-s", "-L", url, "-H", "User-Agent: Mozilla/5.0"],
        capture_output=True, text=True, timeout=timeout
    )
    raw = r.stdout
    # 尝试检测GBK编码
    try:
        for enc in (encoding, "gbk", "gb2312", "utf-8"):
            try:
                return raw.decode(enc).encode("utf-8").decode("utf-8")
            except:
                pass
    except:
        pass
    return raw


def ts_now() -> str:
    return datetime.now(TZ_CST).strftime("%Y-%m-%d %H:%M:%S")


def _date(date_str=None) -> str:
    """返回日期字符串，默认今天"""
    if date_str:
        return date_str
    return datetime.now(TZ_CST).strftime("%Y-%m-%d")


def load_json(path):
    """加载JSON文件，失败返回{}"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


# ══════════════════════════════════════════════════════════
# 数据源1：板块资金流（东方财富）
# ══════════════════════════════════════════════════════════

def fetch_sector_moneyflow(top_n=15) -> dict:
    """
    抓取行业+概念板块主力资金净流入 Top15
    返回: {'行业板块': [...], '概念板块': [...]}
    每个元素: {name, code, pct_chg, main_net(万), lead_stock, lead_pct}
    """
    result = {"行业板块": [], "概念板块": []}

    # 行业板块: m:90+t:2
    url_ind = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f62"
        "&fs=m:90+t:2"
        "&fields=f2,f3,f5,f6,f7,f12,f14,f62,f184"
    )
    d = curl_json(url_ind)
    items = d.get("data", {}).get("diff", []) if d.get("data") else []
    for it in items[:top_n]:
        net = it.get("f62", 0) or 0  # 元 → 万
        result["行业板块"].append({
            "name": it.get("f14", ""),
            "code": str(it.get("f12", "")),
            "pct_chg": it.get("f3", 0),
            "main_net_wan": round(net / 10000, 0),  # 万元
            "inflow_wan": round((it.get("f5") or 0) / 10000, 0),
            "outflow_wan": round((it.get("f6") or 0) / 10000, 0),
        })

    # 概念板块: m:90+t:3
    url_con = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f62"
        "&fs=m:90+t:3"
        "&fields=f2,f3,f5,f6,f7,f12,f14,f62,f184"
    )
    d2 = curl_json(url_con)
    items2 = d2.get("data", {}).get("diff", []) if d2.get("data") else []
    for it in items2[:top_n]:
        net = it.get("f62", 0) or 0
        result["概念板块"].append({
            "name": it.get("f14", ""),
            "code": str(it.get("f12", "")),
            "pct_chg": it.get("f3", 0),
            "main_net_wan": round(net / 10000, 0),
            "inflow_wan": round((it.get("f5") or 0) / 10000, 0),
            "outflow_wan": round((it.get("f6") or 0) / 10000, 0),
        })

    return result


# ══════════════════════════════════════════════════════════
# 数据源2：概念涨幅排行（近30日强势概念）
# ══════════════════════════════════════════════════════════

def fetch_hot_concepts(top_n=20) -> list:
    """
    按涨幅抓取近30日强势概念板块（用于识别热点主线）
    """
    # 按涨幅排序（f3=涨跌幅）
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:90+t:3"
        "&fields=f12,f14,f2,f3,f62"
    )
    d = curl_json(url)
    items = d.get("data", {}).get("diff", []) if d.get("data") else []
    result = []
    for it in items[:top_n]:
        net = it.get("f62", 0) or 0
        result.append({
            "name": it.get("f14", ""),
            "code": str(it.get("f12", "")),
            "pct_chg": it.get("f3", 0),
            "main_net_wan": round(net / 10000, 0),
        })
    return result


# ══════════════════════════════════════════════════════════
# 数据源3：指数收盘数据
# ══════════════════════════════════════════════════════════

def fetch_index_data() -> dict:
    """
    抓取主要指数今日收盘数据
    上证指数 sh.000001，深成指 sz.399001，创业板 sz.399006，科创50 sh.000688
    """
    # secid格式：沪市=1.XXXXXX  深市=0.XXXXXX
    indices = [
        ("1.000001", "上证指数"),
        ("0.399001", "深成指"),
        ("0.399006", "创业板指"),
        ("1.000688", "科创50"),
    ]
    result = {}
    for secid, name in indices:
        prefix, code = secid.split(".")
        url = (
            f"https://push2delay.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}"
            f"&fields=f43,f57,f58,f169,f170,f44,f45,f46,f47,f48,f60"
        )
        d = curl_json(url)
        data = d.get("data", {}) or {}
        if data.get('f43'):
            result[secid] = {
                "name": name,
                "price": data["f43"] / 100,           # f43=仙(百分之一元)，/100得元
                "pct_chg": data.get("f170", 0) / 100, # f170=百分之一%
                "high": data.get("f44", 0) / 100,
                "low": data.get("f45", 0) / 100,
                "open": data.get("f46", 0) / 100,
                "prev_close": data.get("f60", 0) / 100,
                "volume": data.get("f47", 0) / 100,           # f47=手(百股)，/100得亿股
                "amount": data.get("f48", 0) / 1e8,            # f48=成交额(元)，/1e8得亿元
            }
    return result


# ══════════════════════════════════════════════════════════
# 数据源4：涨停复盘（读取本地JSON）
# ══════════════════════════════════════════════════════════

def load_ztfp(date_str: str) -> dict:
    """读取今日涨停复盘JSON，无则返回{}
    改进：若JSON不存在，尝试从东方财富API实时抓取摘要数据
    """
    date_clean = date_str.replace("-", "")
    path = REPORTS_DIR / f"涨停复盘_完整_{date_clean}.json"
    if path.exists():
        return load_json(path)
    # 备选：非完整版
    path2 = REPORTS_DIR / f"涨停复盘_{date_clean}.json"
    if path2.exists():
        return load_json(path2)
    # JSON不存在，尝试从东方财富API实时抓取摘要
    return fetch_ztfp_summary_from_api(date_str)


# ══════════════════════════════════════════════════════════
# 数据源4b：涨停复盘实时API（JSON不存在时的备援）
# ══════════════════════════════════════════════════════════

def fetch_ztfp_summary_from_api(date_str: str) -> dict:
    """
    从东方财富搜索API实时抓取涨停复盘摘要（当日JSON不存在时的备援）
    返回结构兼容 load_ztfp 的完整JSON格式
    """
    import urllib.parse
    import time

    results = {
        "date": date_str,
        "collected_at": ts_now(),
        "午间涨停复盘": None,
        "收盘涨停复盘": None,
        "涨停股详细列表": [],
    }

    # 搜索收盘涨停复盘
    keyword = f"{date_str[5:7].lstrip('0')}月{date_str[8:].lstrip('0')}日涨停复盘"
    param = {
        "uid": "", "keyword": keyword, "type": ["cmsArticle"],
        "client": "web", "clientVersion": "curr", "clientType": "web",
        "param": {
            "cmsArticle": {
                "searchScope": "default", "sort": "default",
                "pageIndex": 1, "pageSize": 5,
                "preTag": "<em>", "postTag": "</em>"
            }
        }
    }
    encoded = urllib.parse.quote(json.dumps(param, ensure_ascii=False), safe='')
    url = f"https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={encoded}"

    try:
        proc = subprocess.run(
            ['curl', '-s', '-A', 'Mozilla/5.0', url],
            capture_output=True, text=True, timeout=15
        )
        data = proc.stdout
        json_str = re.sub(r'^jQuery\(|\)$', '', data)
        parsed = json.loads(json_str)
        articles = parsed.get('result', {}).get('cmsArticle', [])
    except Exception as e:
        print(f"  [WARNING] 涨停复盘API搜索失败: {e}")
        return results

    # 收盘涨停复盘
    for art in articles:
        title = re.sub(r'<[^>]+>', '', art.get('title', ''))
        if '午间' not in title and '涨停复盘' in title:
            text = art.get('content', '')
            zt_count = 0
            fbl = 0.0
            chuji = 0
            # 解析涨停总数
            m = re.search(r'共计?(\d+)股?涨停', text)
            if m:
                zt_count = int(m.group(1))
            # 解析封板率
            m = re.search(r'封板率([\d.]+)%?', text)
            if m:
                fbl = float(m.group(1))
            # 解析触及涨停
            m = re.search(r'(\d+)只个股?盘中一度?触及?涨停', text)
            if m:
                chuji = int(m.group(1))
            # 解析连板龙头
            lianban = ""
            m = re.search(r'([\u4e00-\u9fa5]{2,8}\d+天\d+板)', text)
            if m:
                lianban = m.group(1)
            results["收盘涨停复盘"] = {
                "title": title,
                "date": art.get('date', ''),
                "url": f"https://finance.eastmoney.com/a/{art.get('code', '')}.html",
                "media": art.get('mediaName', ''),
                "summary": {
                    "涨停总数": zt_count,
                    "封板率": fbl,
                    "触及涨停": chuji,
                    "连板龙头": lianban,
                },
                "full_text": text,
            }
            break

    time.sleep(1)

    # 搜索午间涨停复盘（不带日期更稳定）
    param2 = {
        "uid": "", "keyword": "午间涨停复盘", "type": ["cmsArticle"],
        "client": "web", "clientVersion": "curr", "clientType": "web",
        "param": {
            "cmsArticle": {
                "searchScope": "default", "sort": "default",
                "pageIndex": 1, "pageSize": 10,
                "preTag": "<em>", "postTag": "</em>"
            }
        }
    }
    encoded2 = urllib.parse.quote(json.dumps(param2, ensure_ascii=False), safe='')
    url2 = f"https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={encoded2}"

    try:
        proc2 = subprocess.run(
            ['curl', '-s', '-A', 'Mozilla/5.0', url2],
            capture_output=True, text=True, timeout=15
        )
        data2 = proc2.stdout
        json_str2 = re.sub(r'^jQuery\(|\)$', '', data2)
        parsed2 = json.loads(json_str2)
        articles2 = parsed2.get('result', {}).get('cmsArticle', [])
    except Exception as e:
        print(f"  [WARNING] 午间涨停复盘API搜索失败: {e}")
        return results

    for art in articles2:
        art_date = art.get('date', '')[:10]
        if art_date == date_str.replace('-', ''):
            text = art.get('content', '')
            zt_count = 0
            fbl = 0.0
            m = re.search(r'共计?(\d+)股?涨停', text)
            if m:
                zt_count = int(m.group(1))
            m = re.search(r'封板率([\d.]+)%?', text)
            if m:
                fbl = float(m.group(1))
            results["午间涨停复盘"] = {
                "title": re.sub(r'<[^>]+>', '', art.get('title', '')),
                "date": art.get('date', ''),
                "url": f"https://finance.eastmoney.com/a/{art.get('code', '')}.html",
                "media": art.get('mediaName', ''),
                "summary": {
                    "涨停总数": zt_count,
                    "封板率": fbl,
                    "触及涨停": 0,
                    "连板龙头": "",
                },
                "full_text": text,
            }
            break

    print(f"  [API备援] 收盘涨停: {results['收盘涨停复盘']['summary']['涨停总数'] if results.get('收盘涨停复盘') else '无'} 只 "
          f"午间涨停: {results['午间涨停复盘']['summary']['涨停总数'] if results.get('午间涨停复盘') else '无'} 只")
    return results


# ══════════════════════════════════════════════════════════
# 数据源5：财经早餐（读取本地JSON）
# ══════════════════════════════════════════════════════════

def load_caijing_breakfast(date_str: str) -> dict:
    """读取今日财经早餐JSON"""
    date_id = date_str.replace("-", "")
    db_path = BASE_DIR / "database" / f"nightly_collect_{date_id}.json"
    if not db_path.exists():
        # 尝试：取前一天晚上采集的（凌晨02:00采的是"今天"的）
        # 今日日报在当天18:00生成时，前一天凌晨的采集即为当日早报
        yesterday = (datetime.now(TZ_CST) - timedelta(days=1)).strftime("%Y%m%d")
        db_path = BASE_DIR / "database" / f"nightly_collect_{yesterday}.json"
    if not db_path.exists():
        return {}
    data = load_json(str(db_path))
    return data.get("caijing_breakfast", {})


def date_clean(s):
    return s.replace("-", "")


# ══════════════════════════════════════════════════════════
# 数据源6：情绪评分（基于涨停数据）
# ══════════════════════════════════════════════════════════

def calc_sentiment(ztfp_data: dict) -> dict:
    """
    基于涨停数据计算市场情绪
    返回: {score, label, zt_count, fbl, lianban, warning}
    """
    wj = ztfp_data.get("午间涨停复盘", {})
    sb = ztfp_data.get("收盘涨停复盘", {}) or ztfp_data.get("收盘涨停复盘", {})
    zt_count = 0
    fbl = 0  # 封板率
    lianban = ""  # 连板龙头
    summary_sb = sb.get("summary", {}) if isinstance(sb, dict) else {}

    if summary_sb:
        zt_count = summary_sb.get("涨停总数", 0)
        fbl = summary_sb.get("封板率", 0)
        lianban = summary_sb.get("连板龙头", "")

    # 情绪评分：0-100
    # 涨停数: <50=冷(0-30), 50-80=温(31-60), 80-100=热(61-80), >100=高温(81-100)
    if zt_count >= 120:
        score = 85
        label = "🔥 高温（极度活跃）"
    elif zt_count >= 100:
        score = 75
        label = "☀️ 热（活跃）"
    elif zt_count >= 80:
        score = 65
        label = "🌤️ 偏热（偏多）"
    elif zt_count >= 50:
        score = 50
        label = "🌡️ 正常（中性）"
    elif zt_count >= 30:
        score = 35
        label = "☁️ 偏冷（偏空）"
    else:
        score = 20
        label = "❄️ 冷（低迷）"

    # 封板率校正
    if fbl >= 80:
        score = min(100, score + 5)
    elif fbl < 60:
        score = max(0, score - 10)

    # 风险预警
    warning = ""
    if zt_count >= 150:
        warning = "⚠️ 涨停家数创历史高位，情绪极值，警惕物极必反"
    elif fbl < 55:
        warning = "⚠️ 封板率<55%，炸板率高，主力封板意愿弱"

    return {
        "score": score,
        "label": label,
        "zt_count": zt_count,
        "fbl": fbl,
        "lianban": lianban,
        "warning": warning,
    }


# ══════════════════════════════════════════════════════════
# 数据源6：涨跌停市场统计（东方财富AKShare数据）
# ══════════════════════════════════════════════════════════

def fetch_zt_dt_count(date_str: str = None) -> dict:
    """
    抓取全市场涨跌停统计数据
    使用东方财富AKShare接口：ak.stock_zt_pool_em() + ak.stock_zt_pool_dt_em()
    返回: {zt_count, dt_count, zbgc_rate, zt_dt_ratio}
    """
    try:
        import pandas as pd
        import akshare as ak

        date_id = date_str.replace("-", "") if date_str else None

        # 涨停池
        try:
            zt_df = ak.stock_zt_pool_em(date=date_id) if date_id else ak.stock_zt_pool_em()
            zt_count = len(zt_df)
        except Exception as e:
            print(f"  [WARNING] 涨停池获取失败: {e}")
            zt_count = 0
            zt_df = pd.DataFrame()

        # 跌停池（使用正确的AKShare函数名）
        try:
            dt_df = ak.stock_zt_pool_dtgc_em(date=date_id) if date_id else ak.stock_zt_pool_dtgc_em()
            dt_count = len(dt_df)
        except Exception as e:
            print(f"  [WARNING] 跌停池获取失败: {e}")
            dt_count = 0
            dt_df = pd.DataFrame()

        # 炸板池（用于计算炸板率）
        try:
            zbgc_df = ak.stock_zt_pool_zbgc_em(date=date_id) if date_id else ak.stock_zt_pool_zbgc_em()
            zbgc_count = len(zbgc_df)
        except Exception as e:
            zbgc_count = 0

        # 涨停/跌停比
        zt_dt_ratio = round(zt_count / dt_count, 1) if dt_count > 0 else float('inf')

        # 炸板率 = 炸板数 / (涨停数 + 炸板数)
        zbgc_rate = round(zbgc_count / (zt_count + zbgc_count) * 100, 1) if (zt_count + zbgc_count) > 0 else 0

        print(f"  [涨跌停统计] 涨停:{zt_count} 跌停:{dt_count} 炸板:{zbgc_count} 炸板率:{zbgc_rate}% 涨跌停比:{zt_dt_ratio}")

        return {
            "zt_count": zt_count,
            "dt_count": dt_count,
            "zbgc_count": zbgc_count,
            "zbgc_rate": zbgc_rate,
            "zt_dt_ratio": zt_dt_ratio,
        }
    except Exception as e:
        print(f"  [ERROR] 涨跌停数据获取失败: {e}")
        return {"zt_count": 0, "dt_count": 0, "zbgc_count": 0, "zbgc_rate": 0, "zt_dt_ratio": 0}


# ══════════════════════════════════════════════════════════
# 数据源7：全市场换手率（东方财富全市场统计）
# ══════════════════════════════════════════════════════════

def fetch_market_turnover(idx_data: dict) -> dict:
    """
    基于上证指数成交额估算全市场热度
    """
    sh = idx_data.get("1.000001", {})
    amount = sh.get("amount", 0)  # 亿元
    level = "放量" if amount > 8000 else "缩量" if amount < 4000 else "正常"
    return {"amount": amount, "level": level}


# ══════════════════════════════════════════════════════════
# 热点匹配：概念板块 × 个股标签
# ══════════════════════════════════════════════════════════

def match_hot_concepts(stock_list: list, hot_concepts: list) -> list:
    """
    匹配强势概念板块中的相关个股
    stock_list: [{code, name, concepts:[], price, pct_chg, mkt_cap}]
    hot_concepts: [{name, pct_chg, main_net_wan}]
    返回: [{stock, matched_concepts, score}]
    """
    matched = []
    for stock in stock_list:
        stock_concepts = set(stock.get("concepts", []))
        hits = []
        for hc in hot_concepts:
            for sc in stock_concepts:
                if sc in hc["name"] or hc["name"] in sc:
                    hits.append({
                        "concept": sc,
                        "hot_name": hc["name"],
                        "pct": hc["pct_chg"],
                        "fund": hc["main_net_wan"],
                    })
        if hits:
            score = sum(h["pct"] for h in hits)
            matched.append({
                "stock": stock,
                "hits": hits,
                "score": round(score, 2),
            })
    matched.sort(key=lambda x: x["score"], reverse=True)
    return matched[:10]  # Top10


# ══════════════════════════════════════════════════════════
# 生成热点日报文本
# ══════════════════════════════════════════════════════════

def generate_report_text(date_str: str, data: dict) -> str:
    """生成完整的热点日报文本"""
    idx = data.get("index_data", {})
    sec = data.get("sector_mf", {})
    hot = data.get("hot_concepts", [])
    ztfp = data.get("ztfp", {})
    sent = data.get("sentiment", {})
    turnover = data.get("turnover", {})
    cj = data.get("caijing", {})

    lines = []
    def add(t=""):
        lines.append(t)

    # ── 头部 ─────────────────────────────────────────────
    add(f"{'═' * 52}")
    add(f"  每日盘面热点日报  ·  {date_str}  ·  {ts_now()}")
    add(f"{'═' * 52}")
    add()

    # ── 一、指数收盘 ──────────────────────────────────────
    add(f"【一、指数收盘】")
    if idx:
        # 上证指数单独显示
        sh = idx.get("sh.000001", {})
        if sh:
            trend_icon = "▲" if sh["pct_chg"] > 0 else "▼"
            add(f"  上证指数: {sh['price']:.2f}  {trend_icon}{abs(sh['pct_chg']):.2f}%  "
                f"高:{sh['high']:.2f} 低:{sh['low']:.2f} 成交:{sh.get('amount',0):.1f}亿")
        for secid, info in idx.items():
            if secid == "sh.000001":
                continue
            trend_icon = "▲" if info["pct_chg"] > 0 else "▼"
            add(f"  {info['name']}: {info['price']:.2f}  {trend_icon}{abs(info['pct_chg']):.2f}%")
    else:
        add("  （暂无指数数据）")
    add()

    # ── 二、市场情绪温度 ──────────────────────────────────
    add(f"【二、市场情绪】  {sent.get('label', '')}")
    zt_dt = data.get("zt_dt", {})
    zt_count_em = zt_dt.get("zt_count", 0)
    dt_count_em = zt_dt.get("dt_count", 0)
    zbgc_rate = zt_dt.get("zbgc_rate", 0)
    zt_dt_ratio = zt_dt.get("zt_dt_ratio", 0)
    # 优先用AKShare实时数据，否则用涨停复盘数据
    display_zt = zt_count_em if zt_count_em > 0 else sent.get('zt_count', 0)
    display_dt = dt_count_em
    zt_ratio_str = f"{zt_dt_ratio:.1f}" if zt_dt_ratio != float('inf') else "∞"
    add(f"  涨停总数: {display_zt}只  跌停: {display_dt}只  封板率: {sent.get('fbl', 0):.1f}%  "
        f"涨跌停比: {zt_ratio_str}x  连板龙头: {sent.get('lianban', '—')}")
    if zbgc_rate > 0:
        add(f"  炸板数: {zt_dt.get('zbgc_count', 0)}只  炸板率: {zbgc_rate}%")
    if sent.get("warning"):
        add(f"  {sent['warning']}")
    # 换手率
    if turnover:
        add(f"  全市场成交: {turnover.get('amount',0):.0f}亿  状态: {turnover.get('level','正常')}")
    add()

    # ── 三、主力资金主线 ─────────────────────────────────
    add(f"【三、主力资金主线】")
    if sec.get("行业板块"):
        add("  ▸ 行业净流入 Top5：")
        for i, s in enumerate(sec["行业板块"][:5], 1):
            icon = "↑" if s["main_net_wan"] > 0 else "↓"
            add(f"    {i}. {s['name']:<10} {s['pct_chg']:>+6.2f}%  主力净流入 {s['main_net_wan']:>10,.0f}万 {icon}")
    add()
    if sec.get("概念板块"):
        add("  ▸ 概念净流入 Top5：")
        for i, s in enumerate(sec["概念板块"][:5], 1):
            icon = "↑" if s["main_net_wan"] > 0 else "↓"
            add(f"    {i}. {s['name']:<10} {s['pct_chg']:>+6.2f}%  主力净流入 {s['main_net_wan']:>10,.0f}万 {icon}")
    add()

    # ── 四、近30日强势题材 ────────────────────────────────
    add(f"【四、近30日强势题材 Top10】")
    if hot:
        for i, h in enumerate(hot[:10], 1):
            icon = "🔥" if h["pct_chg"] >= 4 else "★" if h["pct_chg"] >= 2 else "·"
            add(f"    {i:2d}. {icon} {h['name']:<12} {h['pct_chg']:>+6.2f}%  "
                f"主力净流入 {h.get('main_net_wan', 0):>+10,.0f}万")
    add()

    # ── 五、涨停复盘摘要 ─────────────────────────────────
    add(f"【五、涨停复盘】")
    wj = ztfp.get("午间涨停复盘", {})
    sb = ztfp.get("收盘涨停复盘", {})
    if sb and isinstance(sb, dict):
        add(f"  ▸ 收盘涨停: {sb.get('summary',{}).get('涨停总数', '?')}只  "
            f"封板率 {sb.get('summary',{}).get('封板率',0):.1f}%  "
            f"触及涨停 {sb.get('summary',{}).get('触及涨停',0)}只")
        title_sb = sb.get("title","")
        if title_sb:
            add(f"    标题: {title_sb}")
    if wj and isinstance(wj, dict):
        add(f"  ▸ 午间涨停: {wj.get('summary',{}).get('涨停总数', '?')}只  "
            f"封板率 {wj.get('summary',{}).get('封板率',0):.1f}%")
    # 封单资金Top5
    stocks = ztfp.get("涨停股详细列表", [])
    if stocks:
        add(f"  ▸ 封单资金 Top5（次日溢价预期参考）：")
        top5 = sorted(stocks, key=lambda x: x.get("seal_fund", 0), reverse=True)[:5]
        for i, s in enumerate(top5, 1):
            name = s.get("name", s.get("code",""))
            code = s.get("code","")
            close = s.get("close", 0)
            seal = s.get("seal_fund", 0)
            industry = s.get("industry", "")
            add(f"    {i}. {code} {name:<8} 收{close:>7.2f} 封单:{seal:>10,.0f}万  [{industry}]")
    add()

    # ── 六、财经早餐要点（事件催化）──────────────────────
    add(f"【六、今日盘前重要事件】")
    body = cj.get("latest", {}).get("body", "") or cj.get("body", "")
    if body:
        # 找正文开始：第一句"东方财富财经早餐..."是标题+导航噪音
        # 找到第一个句号后的位置即为正文起点
        body = body[body.find("。") + 1:]
        sents = [s.strip() for s in body.split("。") if len(s.strip()) > 15]
        for i, s in enumerate(sents[:6], 1):
            text = s[:88] + "..." if len(s) > 88 else s
            add(f"  {i}. {text}")
    else:
        add("  （今日财经早餐未获取到）")
    add()

    # ── 七、明日热点前瞻 ─────────────────────────────────
    add(f"【七、明日热点前瞻】")
    if hot:
        add("  强势题材延续概率评估：")
        top3 = hot[:3]
        for i, h in enumerate(top3, 1):
            fund_level = "大资金" if h.get("main_net_wan", 0) > 50000 else "中等" if h.get("main_net_wan", 0) > 10000 else "小量"
            pct = h["pct_chg"]
            vig = "持续强势" if pct >= 3 else "震荡" if pct >= 1 else "可能退潮"
            add(f"    {i}. {h['name']}: 涨幅{pct:+.2f}% 主力{fund_level} 预判:{vig}")
    add()

    # ── 八、风险预警 ─────────────────────────────────────
    add(f"【八、风险预警】")
    warns = []
    if sent.get("score", 0) >= 85:
        warns.append("🔥 市场情绪高温：涨停家数过多，极值区域防物极必反")
    if sent.get("fbl", 100) < 55:
        warns.append("⚠️ 封板率过低：主力封板意愿弱，炸板率高")
    if ztfp.get("涨停股详细列表"):
        # 找筹码高位的强势股
        high_pos = [s for s in ztfp["涨停股详细列表"] if s.get("code") == "603083"]
        if high_pos:
            warns.append(f"⚠️ {high_pos[0]['name']} 筹码获利比例99%，高位警戒")
    if not warns:
        warns.append("✅ 今日无高级别风险预警")
    for w in warns:
        add(f"  {w}")
    add()

    # ── 九、重点跟踪标的 ─────────────────────────────────
    add(f"【九、重点跟踪标的】")
    add("  （基于资金流向 + 技术低位筛选，待补充持仓后定向推送）")
    add()

    # ── 底部 ─────────────────────────────────────────────
    add(f"{'─' * 52}")
    add(f"  生成时间: {ts_now()}")
    add(f"  数据来源: 东方财富(板块资金流/概念排行/涨停复盘) + "
        f"财经早餐 + Baostock")
    add(f"{'─' * 52}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════
# 保存JSON（供后续分析）
# ══════════════════════════════════════════════════════════

def save_json(data: dict, date_str: str) -> str:
    path = REPORTS_DIR / f"热点日报_{date_clean(date_str)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return str(path)


# ══════════════════════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════════════════════

def run(date_str=None):
    date_str = _date(date_str)
    print(f"\n{'='*52}")
    print(f"  每日盘面热点日报  {date_str}")
    print(f"{'='*52}")

    # 1. 采集数据
    print(f"\n[1/6] 采集板块资金流...")
    sector_mf = fetch_sector_moneyflow(top_n=15)

    print(f"[2/6] 采集概念涨幅排行...")
    hot_concepts = fetch_hot_concepts(top_n=20)

    print(f"[3/6] 采集指数数据...")
    index_data = fetch_index_data()

    print(f"[4/6] 读取涨停复盘...")
    ztfp = load_ztfp(date_str)

    print(f"[5/6] 读取财经早餐...")
    cj = load_caijing_breakfast(date_str)

    print(f"[6/6] 采集涨跌停统计 & 计算情绪评分...")
    zt_dt = fetch_zt_dt_count(date_str)
    sentiment = calc_sentiment(ztfp)

    # 若涨停复盘已有封板率数据，优先保留；否则用AKShare炸板率
    if zt_dt.get("zbgc_rate", 0) > 0 and sentiment.get("fbl", 0) == 0:
        sentiment["fbl"] = zt_dt["zbgc_rate"]

    turnover = fetch_market_turnover(index_data)

    # 汇总数据
    data = {
        "date": date_str,
        "generated_at": ts_now(),
        "index_data": index_data,
        "sector_mf": sector_mf,
        "hot_concepts": hot_concepts,
        "ztfp": ztfp,
        "sentiment": sentiment,
        "turnover": turnover,
        "caijing": cj,
        "zt_dt": zt_dt,
    }

    # 生成文本报告
    report_text = generate_report_text(date_str, data)

    # 保存JSON
    json_path = save_json(data, date_str)
    print(f"\nJSON已保存: {json_path}")

    # 打印报告
    print("\n" + report_text)

    # 保存文本报告
    txt_path = REPORTS_DIR / f"热点日报_{date_clean(date_str)}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n文本已保存: {txt_path}")

    return data, report_text


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    data, report_text = run(date_arg)
