#!/usr/bin/env python3
"""gstc_nightly_collect.py - 凌晨2点数据采集
采集：行业板块+概念板块+大盘资金流+热点题材
输出：~/stock_knowledge/database/nightly_collect_YYYYMMDD.json
"""
import json
import subprocess
import sys
from datetime import datetime

OUTDIR = "/home/admin/stock_knowledge/database"

def curl_json(url, referer=""):
    cmd = [
        "curl", "-s", url,
        "-H", f"User-Agent: Mozilla/5.0",
        "-H", f"Referer: {referer}" if referer else "User-Agent: Mozilla/5.0"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return json.loads(result.stdout)

def fetch_industry_money_top20():
    """行业板块资金流 Top20"""
    url = ("https://push2delay.eastmoney.com/api/qt/clist/get?"
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
    url = ("https://push2delay.eastmoney.com/api/qt/clist/get?"
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
    url = ("https://push2delay.eastmoney.com/api/qt/clist/get?"
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
    url = ("https://push2delay.eastmoney.com/api/qt/clist/get?"
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

    result = {
        "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "industry_money_top20": industry_money,
        "concept_money_top20": concept_money,
        "industry_hot_top10": industry_hot,
        "concept_hot_top10": concept_hot,
        "index_money": index_money
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
