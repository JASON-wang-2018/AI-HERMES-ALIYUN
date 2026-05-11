#!/usr/bin/env python3
"""gstc_nightly_collect.py - 凌晨2点数据采集
采集：行业板块+概念板块+大盘资金流+热点题材+财经早餐
输出：~/stock_knowledge/database/nightly_collect_YYYYMMDD.json
"""
import json
import subprocess
import sys
import re
from datetime import datetime, timedelta

OUTDIR = "/home/admin/stock_knowledge/database"


def curl_json(url, referer=""):
    cmd = [
        "curl", "-s", url,
        "-H", "User-Agent: Mozilla/5.0",
        "-H", f"Referer: {referer}" if referer else ""
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return json.loads(result.stdout)


def fetch_industry_money_top20():
    """行业板块资金流 Top20"""
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=20&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
        "&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f2,f3,f62,f184")
    d = curl_json(url, "https://data.eastmoney.com/bkzj/hy.html")
    items = []
    for r in sorted(d["data"]["diff"], key=lambda x: x["f62"], reverse=True)[:20]:
        items.append({
            "name": r["f14"],
            "price": round(r["f2"] / 100, 2),
            "pct": round(r["f3"] / 100, 2),
            "main_net": round(r["f62"] / 1e8, 2)
        })
    return items


def fetch_concept_money_top20():
    """概念板块资金流 Top20"""
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=20&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
        "&fltt=2&invt=2&fid=f62&fs=m:90+t:3&fields=f12,f14,f2,f3,f62,f184")
    d = curl_json(url, "https://data.eastmoney.com/bkzj/gn.html")
    items = []
    for r in sorted(d["data"]["diff"], key=lambda x: x["f62"], reverse=True)[:20]:
        items.append({
            "name": r["f14"],
            "price": round(r["f2"] / 100, 2),
            "pct": round(r["f3"] / 100, 2),
            "main_net": round(r["f62"] / 1e8, 2)
        })
    return items


def fetch_industry_hot_top10():
    """行业板块涨跌榜 Top10"""
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=10&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
        "&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f12,f14,f2,f3,f62")
    d = curl_json(url, "https://data.eastmoney.com/bkzj/hy.html")
    items = []
    for r in sorted(d["data"]["diff"], key=lambda x: x["f3"], reverse=True)[:10]:
        items.append({
            "name": r["f14"],
            "pct": round(r["f3"] / 100, 2),
            "main_net": round(r["f62"] / 1e8, 2)
        })
    return items


def fetch_concept_hot_top10():
    """概念板块涨跌榜 Top10"""
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=10&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
        "&fltt=2&invt=2&fid=f3&fs=m:90+t:3&fields=f12,f14,f2,f3,f62")
    d = curl_json(url, "https://data.eastmoney.com/bkzj/gn.html")
    items = []
    for r in sorted(d["data"]["diff"], key=lambda x: x["f3"], reverse=True)[:10]:
        items.append({
            "name": r["f14"],
            "pct": round(r["f3"] / 100, 2),
            "main_net": round(r["f62"] / 1e8, 2)
        })
    return items


def fetch_index_money():
    """大盘资金流：上证/深证/创业板"""
    indices = {
        "上证指数": "1.000001",
        "深证成指": "0.399001",
        "创业板指": "0.399006"
    }
    result = {}
    for name, secid in indices.items():
        url = (f"https://push2delay.eastmoney.com/api/qt/stock/fflow/kline/get?"
               f"lmt=1&klt=101&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56&secid={secid}")
        try:
            d = curl_json(url, "https://data.eastmoney.com/zjlx/dpzjlx.html")
            klines = d.get("data", {}).get("klines", [])
            if klines:
                parts = klines[-1].split(",")
                result[name] = {
                    "date": parts[0],
                    "main_net": round(float(parts[1]) / 1e8, 2),
                    "super_large": round(float(parts[2]) / 1e8, 2),
                    "large": round(float(parts[3]) / 1e8, 2),
                    "mid": round(float(parts[4]) / 1e8, 2),
                    "small": round(float(parts[5]) / 1e8, 2)
                }
        except Exception as e:
            result[name] = {"error": str(e)}
    return result


# ── 财经早餐采集 ──────────────────────────────────────────────
def curl_text(url, timeout=25):
    """HTTP GET 返回文本（自动处理gzip）"""
    cmd = [
        "curl", "-s", "--connect-timeout", str(timeout), "-L",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "--compressed",
        url
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    return r.stdout


def extract_content(html):
    """从HTML提取正文文本"""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&')
    html = re.sub(r'\s+', ' ', html).strip()
    return html


def get_topic_article_id(topic_url):
    """
    从东方财富 topic 专题页面提取财经早餐正文URL。
    原理：topic页面的HTML中包含JSON数据块，有完整文章ID和标题。
    返回：(finance_article_id, title)
    """
    body = curl_text(topic_url)
    if not body or len(body) < 1000:
        return None, None

    # 在HTML的script标签JSON中找"东方财富财经早餐"对应的文章code
    # 格式: {"code":"202605063729027393","etype":"CMS","title":"东方财富财经早餐 5月7日周四",...}
    # 找包含"财经早餐"的JSON title字段
    # 用正则：匹配 title 字段及其相邻的 code 字段
    try:
        # 策略：在script标签内容中搜索"东方财富财经早餐"附近，提取code值
        # 由于JSON可能被HTML转义，需要分步处理
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', body, re.DOTALL)
        for script in scripts:
            if len(script.strip()) < 50:
                continue
            # 搜索包含"财经早餐"的片段
            idx = script.find('财经早餐')
            if idx < 0:
                idx = script.find('breakfast')
            if idx < 0:
                continue

            # 提取周围200字符窗口
            window = script[max(0, idx - 200):idx + 200]
            # 提取code
            code_m = re.search(r'"code"\s*:\s*"(\d{10,20})"', window)
            title_m = re.search(r'"title"\s*:\s*"([^"]{5,60})"', window)
            if code_m and title_m:
                return code_m.group(1), title_m.group(1)

            # 也尝试直接搜索"code":"数字"
            # 先找包含"财经早餐"的那段JSON
            if '财经早餐' in script:
                # 搜索"title":"...财经早餐..."格式
                full_title_m = re.search(r'"title"\s*:\s*"([^"]*财经早餐[^"]*)"', script)
                if full_title_m:
                    # 在这段JSON周围找code
                    title_str = full_title_m.group(1)
                    title_idx = script.find(title_str)
                    nearby = script[max(0, title_idx - 300):title_idx + 300]
                    code_m2 = re.search(r'"code"\s*:\s*"(\d{10,20})"', nearby)
                    if code_m2:
                        return code_m2.group(1), title_str
    except Exception as e:
        pass

    return None, None


def fetch_caijing_breakfast():
    """
    采集东方财富财经早餐。
    
    策略：
    1. 列表页 stock.eastmoney.com/a/czpnc.html 提取盘前必读topic链接
    2. 每篇topic页面 → JSON数据中找"东方财富财经早餐"的真实article ID
    3. 抓取finance.eastmoney.com/a/{article_id}.html 正文
    4. 返回最新1篇完整正文
    """
    list_url = "https://stock.eastmoney.com/a/czpnc.html"
    html = curl_text(list_url)

    # ── 步骤1：提取盘前必读列表 ───────────────────────────
    # HTML格式: <span>05月06日</span>&nbsp;<a href="https://topic.eastmoney.com/detail/...">盘前必读5月7日</a>
    pn_items = re.findall(
        r'<span>(\d{2}月\d{2}日)</span>&nbsp;<a href="(https://topic\.eastmoney\.com/detail/[^"]+)"[^>]*>(盘前必读[^<]+)</a>',
        html
    )

    articles = []
    for date_label, topic_url, title in pn_items:
        m = re.search(r'(\d{2})月(\d{2})日', date_label)
        if m:
            month, day = m.groups()
            date_str = f"2026-{month}-{day.zfill(2)}"
        else:
            date_str = ""
        articles.append({
            "date": date_str,
            "date_label": date_label,
            "title": title.strip(),
            "topic_url": topic_url,
            "finance_url": "",
            "body": ""
        })

    # ── 步骤2：从每个topic页面获取真实finance文章ID ────────
    for art in articles:
        article_id, finance_title = get_topic_article_id(art["topic_url"])
        if article_id:
            art["finance_url"] = f"https://finance.eastmoney.com/a/{article_id}.html"
            if finance_title:
                art["title"] = finance_title
            print(f"✅ 盘前必读 {art['date']}: ID={article_id}")

    # ── 步骤3：抓取最新1篇正文 ────────────────────────────
    breakfast_article = None
    for art in articles:
        if not art["finance_url"]:
            continue
        body = curl_text(art["finance_url"])
        if not body or len(body) < 1000:
            continue
        content = extract_content(body)
        # 验证确实是财经早餐内容
        if "财经早餐" in content or "东方财富财经早餐" in content:
            # 找正文起始位置
            for kw in ['东方财富财经早餐', '财经早餐', '盘前必读', '导读']:
                idx = content.find(kw)
                if idx >= 0:
                    art["body"] = content[idx:idx + 6000]
                    break
            else:
                art["body"] = content[:6000]
            breakfast_article = art
            print(f"✅ 财经早餐正文: [{art['title']}] ({len(art['body'])} 字符)")
            break

    latest = breakfast_article if breakfast_article else (articles[0] if articles else {})

    return {
        "list": [{"date": a["date"], "title": a["title"], "finance_url": a["finance_url"], "topic_url": a["topic_url"]} for a in articles],
        "latest": {
            "date": latest.get("date", ""),
            "title": latest.get("title", ""),
            "body": latest.get("body", ""),
            "url": latest.get("finance_url", "")
        }
    }


# ── 主入口 ─────────────────────────────────────────────────────
def main():
    print(f"=== 开始采集 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    try:
        industry_money = fetch_industry_money_top20()
        print(f"✅ 行业板块资金流: {len(industry_money)} 条")
    except Exception as e:
        print(f"❌ 行业板块资金流失败: {e}")
        industry_money = []

    try:
        concept_money = fetch_concept_money_top20()
        print(f"✅ 概念板块资金流: {len(concept_money)} 条")
    except Exception as e:
        print(f"❌ 概念板块资金流失败: {e}")
        concept_money = []

    try:
        industry_hot = fetch_industry_hot_top10()
        print(f"✅ 行业涨跌榜: {len(industry_hot)} 条")
    except Exception as e:
        print(f"❌ 行业涨跌榜失败: {e}")
        industry_hot = []

    try:
        concept_hot = fetch_concept_hot_top10()
        print(f"✅ 概念涨跌榜: {len(concept_hot)} 条")
    except Exception as e:
        print(f"❌ 概念涨跌榜失败: {e}")
        concept_hot = []

    try:
        index_money = fetch_index_money()
        print(f"✅ 大盘资金流: {len(index_money)} 条")
    except Exception as e:
        print(f"❌ 大盘资金流失败: {e}")
        index_money = {}

    # ── 财经早餐采集 ──
    try:
        caijing = fetch_caijing_breakfast()
        print(f"✅ 财经早餐: {caijing['latest']['title'] or '无数据'}")
    except Exception as e:
        print(f"❌ 财经早餐失败: {e}")
        caijing = {"list": [], "latest": {"date": "", "title": "", "body": "", "url": ""}}

    result = {
        "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "industry_money_top20": industry_money,
        "concept_money_top20": concept_money,
        "industry_hot_top10": industry_hot,
        "concept_hot_top10": concept_hot,
        "index_money": index_money,
        "caijing_breakfast": caijing
    }

    today = datetime.now().strftime("%Y%m%d")
    outfile = f"{OUTDIR}/nightly_collect_{today}.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    import os
    size = os.path.getsize(outfile)
    print(f"\n✅ 采集完成: {outfile} ({size} bytes)")
    return result


if __name__ == "__main__":
    main()
