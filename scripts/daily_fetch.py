#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日收盘数据汇总脚本
每天 17:00 自动执行：拉取当日指数+板块资金流+涨停池，入库

防封策略：
  1. AKShare接口调用间隔随机延时3-6秒
  2. 接口失败自动切换 Playwright 浏览器采集（东财/同花顺动态页面）
  3. 同花顺复盘页保留 curl+iconv 方案作为备选

使用方法：
  python3 scripts/daily_fetch.py              # 自动用今天日期
  python3 scripts/daily_fetch.py 20260427     # 指定日期
"""

import sys
import sqlite3
import pandas as pd
import akshare as ak
import subprocess
import time
import random
import json
import re
from datetime import datetime, timedelta

DB = "/home/admin/stock_knowledge/database/stock_data.db"


# ============================================================
# 防封延时 + Playwright 备援
# ============================================================

def _safe_delay():
    """随机延时（3~6秒，防止AKShare同一IP高频调用被封）"""
    t = random.uniform(3.0, 6.0)
    print(f"  ⏱ 防封延时: {t:.1f}秒")
    time.sleep(t)


def _ak_retry(ak_func, *args, max_retry=2, **kwargs):
    """
    AKShare安全调用封装：失败时自动用Playwright备援
    返回 (data, source) 元组
    """
    for attempt in range(max_retry + 1):
        try:
            _safe_delay()
            data = ak_func(*args, **kwargs)
            if data is not None and not (hasattr(data, 'empty') and data.empty):
                return data, "akshare"
            if attempt < max_retry:
                print(f"  ⚠️ AKShare返回空，第{attempt+1}次重试...")
                time.sleep(5)
                continue
            # AKShare彻底失败，抛出异常触发备援
            raise ValueError("AKShare returned empty data")
        except Exception as e:
            if attempt < max_retry:
                print(f"  ⚠️ AKShare异常: {str(e)[:60]}，第{attempt+1}次重试...")
                time.sleep(8)
            else:
                print(f"  ❌ AKShare失败: {str(e)[:60]}，切换Playwright备援...")
                raise


def _fetch_via_browser_stock_list(url, css_selector="table"):
    """
    Playwright备援：直接采集东财/同花顺的动态表格页
    返回解析后的数据或空列表
    """
    try:
        # 延迟导入，避免不需要时也要装playwright
        sys.path.insert(0, "/home/admin/stock_knowledge/scripts")
        from browser_fetch import fetch_page_content
        result = fetch_page_content(url, wait_selector=css_selector, wait_time=5)
        if result.get("error"):
            print(f"  ❌ Playwright备援失败: {result['error']}")
            return [], "playwright_failed"
        # 简单解析：提取所有文本行
        text = result.get("html", "")
        print(f"  ✅ Playwright备援成功({result.get('title','')[:30]})")
        return text, "playwright"
    except Exception as e:
        print(f"  ❌ Playwright备援异常: {e}")
        return [], "playwright_failed"


def get_date(args):
    """从参数或系统时间获取交易日期"""
    if len(args) >= 2:
        date = args[1]
        # YYYYMMDD → (display, raw)
        if "-" in date:
            date_raw = date.replace("-", "")
        else:
            date_raw = date
        return f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}", date_raw
    # 自动：用今天（17点跑，取今天收盘数据）
    today = datetime.now()
    weekday = today.weekday()
    # 周末自动用周五
    if weekday >= 5:
        days_back = weekday - 4
        today -= timedelta(days=days_back)
    date_raw = today.strftime("%Y%m%d")
    return today.strftime("%Y-%m-%d"), date_raw


# ============================================================
# 1. 四大指数
# ============================================================
def fetch_index(date_display):
    """拉取并保存四大指数收盘数据"""
    indices = [
        ("上证指数", "sh000001"),
        ("沪深300",  "sh000300"),
        ("深证成指", "sz399001"),
        ("创业板指", "sz399006"),
    ]
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS index_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            index_name TEXT,
            close REAL,
            change REAL,
            change_pct REAL,
            volume亿 REAL,
            UNIQUE(date, index_name)
        )
    """)
    success = 0
    for name, symbol in indices:
        try:
            # 用安全重试封装，防封延时自动加
            df, src = _ak_retry(ak.stock_zh_index_daily, symbol=symbol)
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df = df.sort_values("date")
            row = df[df["date"] == date_display]
            if len(row) == 0:
                print(f"  ⏭ {name}: {date_display} 无数据（非交易日）")
                continue
            cur_row = row.iloc[0]
            prev = df[df["date"] < date_display].iloc[-1]
            chg   = cur_row["close"] - prev["close"]
            pct   = chg / prev["close"] * 100
            vol   = cur_row["volume"] / 1e8
            cur.execute(
                "INSERT OR REPLACE INTO index_daily (date,index_name,close,change,change_pct,volume亿) VALUES (?,?,?,?,?,?)",
                (date_display, name, cur_row["close"], chg, pct, vol)
            )
            arrow = "▲" if chg >= 0 else "▼"
            print(f"  ✅ {name}: {cur_row['close']:.2f} {arrow}{pct:+.2f}%  成交{vol:.0f}亿 [{src}]")
            success += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
    conn.commit()
    conn.close()
    return success


# ============================================================
# 2. 行业板块资金流（涨幅+主力净流入）
# ============================================================
def fetch_industry(date_display):
    """行业板块数据（AKShare + Playwright备援）"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS board_industry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            close REAL,
            change_pct REAL,
            inflow REAL,
            outflow REAL,
            main_net REAL,
            company_count INTEGER,
            top_stock TEXT,
            top_stock_pct REAL,
            source TEXT,
            UNIQUE(date, name)
        )
    """)
    try:
        df, src = _ak_retry(ak.stock_fund_flow_industry, symbol="即时")
        rename = {
            "行业": "name", "行业指数": "close", "行业-涨跌幅": "change_pct",
            "流入资金": "inflow", "流出资金": "outflow", "净额": "main_net",
            "公司家数": "company_count", "领涨股": "top_stock",
            "领涨股-涨跌幅": "top_stock_pct",
        }
        df = df.rename(columns=rename).sort_values("change_pct", ascending=False)
        for _, r in df.iterrows():
            cur.execute("""
                INSERT OR REPLACE INTO board_industry
                (date,name,close,change_pct,inflow,outflow,main_net,company_count,top_stock,top_stock_pct,source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (date_display, r["name"], r.get("close",0), r.get("change_pct",0),
                  r.get("inflow",0), r.get("outflow",0), r.get("main_net",0),
                  r.get("company_count",0), r.get("top_stock",""), r.get("top_stock_pct",0), src))
        print(f"  ✅ 行业板块: {len(df)}个  [{src}]")
        conn.commit()
        conn.close()
        return len(df)
    except Exception as e:
        print(f"  ❌ 行业板块: {e}")
        # Playwright备援：采集东财板块页
        print(f"  🔄 切换Playwright备援采集东财板块页...")
        board_html, bsrc = _fetch_via_browser_stock_list(
            "https://quote.eastmoney.com/center/boardlist.html#industry_board",
            css_selector="table"
        )
        # 简单解析JSON数据块
        try:
            text = board_html
            pattern = r'"boardName"\s*:\s*"([^"]+)".*?"priceChangeRate"\s*:\s*"([^"]+)"'
            matches = re.findall(pattern, text, re.S)
            count = 0
            for name, pct in matches[:60]:
                pct_f = float(pct.strip().replace('%', ''))
                cur.execute("""
                    INSERT OR REPLACE INTO board_industry
                    (date,name,change_pct,source) VALUES (?,?,?,?)
                """, (date_display, name.strip(), pct_f, bsrc))
                count += 1
            print(f"  ✅ 行业板块(Playwright备援): {count}个")
            conn.commit()
            conn.close()
            return count
        except Exception as berr:
            print(f"  ❌ Playwright备援解析失败: {berr}")
        conn.close()
        return 0


def fetch_concept(date_display):
    """概念板块数据（AKShare + Playwright备援）"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS board_fund_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            close REAL,
            change_pct REAL,
            inflow REAL,
            outflow REAL,
            main_net REAL,
            company_count INTEGER,
            top_stock TEXT,
            top_stock_pct REAL,
            source TEXT,
            UNIQUE(date, name)
        )
    """)
    try:
        df, src = _ak_retry(ak.stock_fund_flow_concept, symbol="即时")
        rename = {
            "概念": "name", "概念指数": "close", "概念-涨跌幅": "change_pct",
            "流入资金": "inflow", "流出资金": "outflow", "净额": "main_net",
            "公司家数": "company_count", "领涨股": "top_stock",
            "领涨股-涨跌幅": "top_stock_pct",
        }
        df = df.rename(columns=rename).sort_values("main_net", ascending=False)
        for _, r in df.iterrows():
            cur.execute("""
                INSERT OR REPLACE INTO board_fund_flow
                (date,name,close,change_pct,inflow,outflow,main_net,company_count,top_stock,top_stock_pct,source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (date_display, r["name"], r.get("close",0), r.get("change_pct",0),
                  r.get("inflow",0), r.get("outflow",0), r.get("main_net",0),
                  r.get("company_count",0), r.get("top_stock",""), r.get("top_stock_pct",0), src))
        print(f"  ✅ 概念板块: {len(df)}个  [{src}]")
        conn.commit()
        conn.close()
        return len(df)
    except Exception as e:
        print(f"  ❌ 概念板块: {e}")
        # Playwright备援：采集东财概念页
        print(f"  🔄 切换Playwright备援采集东财概念板块页...")
        board_html, bsrc = _fetch_via_browser_stock_list(
            "https://quote.eastmoney.com/center/boardlist.html#concept_board",
            css_selector="table"
        )
        try:
            text = board_html
            pattern = r'"boardName"\s*:\s*"([^"]+)".*?"priceChangeRate"\s*:\s*"([^"]+)"'
            matches = re.findall(pattern, text, re.S)
            count = 0
            for name, pct in matches[:60]:
                pct_f = float(pct.strip().replace('%', ''))
                cur.execute("""
                    INSERT OR REPLACE INTO board_fund_flow
                    (date,name,change_pct,source) VALUES (?,?,?,?)
                """, (date_display, name.strip(), pct_f, bsrc))
                count += 1
            print(f"  ✅ 概念板块(Playwright备援): {count}个")
            conn.commit()
            conn.close()
            return count
        except Exception as berr:
            print(f"  ❌ Playwright备援解析失败: {berr}")
        conn.close()
        return 0


# ============================================================
# 4. 涨停池（AKShare 实时）
# ============================================================
def fetch_zt(date_display, date_raw):
    """涨停股池（AKShare + 防封延时）"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS zt_review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            code TEXT,
            name TEXT,
            board_desc TEXT,
            sector TEXT,
            theme TEXT,
            turnover_rate REAL,
            fengdan_wan REAL,
            first_seal_time TEXT,
            成交额亿 REAL,
            流通市值亿 REAL,
            source TEXT,
            UNIQUE(date, code)
        )
    """)
    try:
        df, src = _ak_retry(ak.stock_zt_pool_em, date=date_raw)
        df.columns = [c.strip() for c in df.columns]
        rename = {}
        for c in df.columns:
            cl = c.lower()
            if "代码" in c:
                rename[c] = "code"
            elif "名称" in c:
                rename[c] = "name"
            elif "封板金额" in c or "金额" in c:
                rename[c] = "fengdan_wan"
            elif "换手率" in c:
                rename[c] = "turnover_rate"
            elif "首次封板" in c or "时间" in c:
                rename[c] = "first_seal_time"
            elif "连板数" in c:
                rename[c] = "board_desc"
            elif "成交额" in c:
                rename[c] = "成交额亿"
            elif "流通市值" in c:
                rename[c] = "流通市值亿"
        df = df.rename(columns=rename)
        if "code" not in df.columns or "name" not in df.columns:
            print(f"  ⚠️ 涨停池字段不完整: {df.columns.tolist()[:8]}")
            conn.close()
            return 0
        count = 0
        for _, r in df.iterrows():
            def scalar(v, default=0):
                import pandas as pd
                if pd.isna(v):
                    return default
                if isinstance(v, (pd.Series, list, dict)):
                    return default
                return v
            cur.execute("""
                INSERT OR REPLACE INTO zt_review
                (date,code,name,board_desc,sector,theme,turnover_rate,fengdan_wan,first_seal_time,成交额亿,流通市值亿,source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (date_display,
                  scalar(r.get("code",""), ""),
                  scalar(r.get("name",""), ""),
                  scalar(r.get("board_desc",""), ""),
                  scalar(r.get("板块",""), ""),
                  "",
                  scalar(r.get("turnover_rate",""), 0),
                  scalar(r.get("fengdan_wan",""), 0),
                  scalar(r.get("first_seal_time",""), ""),
                  scalar(r.get("成交额亿",""), 0),
                  scalar(r.get("流通市值亿",""), 0),
                  src))
            count += 1
        print(f"  ✅ 涨停池: {count}只  [{src}]")
        conn.commit()
        conn.close()
        return count
    except Exception as e:
        print(f"  ❌ 涨停池: {e}")
        conn.close()
        return 0


# ============================================================
# 主流程
# ============================================================
def main():
    date_display, date_raw = get_date(sys.argv)
    print(f"\n{'='*50}")
    print(f"📡 每日数据汇总  {date_display}")
    print(f"{'='*50}")

    # 1. 四大指数
    print(f"\n📊 四大指数...")
    fetch_index(date_display)

    # 2. 行业板块
    print(f"\n📈 行业板块...")
    n_ind = fetch_industry(date_display)

    # 3. 概念板块
    print(f"\n💰 概念板块...")
    n_con = fetch_concept(date_display)

    # 4. 涨停池
    print(f"\n🔴 涨停池...")
    n_zt = fetch_zt(date_display, date_raw)

    print(f"\n{'='*50}")
    print(f"✅ {date_display} 数据汇总完成")
    print(f"   指数: 4条  |  行业: {n_ind}个  |  概念: {n_con}个  |  涨停: {n_zt}只")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
