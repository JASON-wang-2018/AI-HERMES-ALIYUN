#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
板块资金流 + 涨幅排名
功能：
  1. 板块涨幅 TOP5 / 跌幅 TOP5
  2. 板块主力净额 TOP5（超大单+大单净流入）
  3. 存入 SQLite 供历史比对

使用：
  python3 scripts/sector_fund_flow.py
  python3 scripts/sector_fund_flow.py 20260427
"""

import sys
import sqlite3
import pandas as pd
import akshare as ak
from datetime import datetime


DB = "/home/admin/stock_knowledge/database/stock_data.db"


def get_board_industry(limit=10):
    """
    获取东方财富行业板块当日涨跌幅排名
    返回: DataFrame
    """
    # 东方财富行业板块资金流（含涨幅+资金流）
    df = ak.stock_fund_flow_industry(symbol="即时")
    rename = {
        "行业": "name",
        "行业指数": "close",
        "行业-涨跌幅": "change_pct",
        "流入资金": "inflow",
        "流出资金": "outflow",
        "净额": "main_net",
        "公司家数": "company_count",
        "领涨股": "top_stock",
        "领涨股-涨跌幅": "top_stock_pct",
    }
    df = df.rename(columns=rename)
    df = df.sort_values("change_pct", ascending=False)
    return df


def get_sector_fund_flow():
    """
    获取概念板块资金流（主力净流入排名）
    返回: DataFrame
    """
    df = ak.stock_fund_flow_concept(symbol="即时")
    rename = {
        "行业": "name",
        "行业指数": "close",
        "行业-涨跌幅": "change_pct",
        "流入资金": "inflow",
        "流出资金": "outflow",
        "净额": "main_net",
        "公司家数": "company_count",
        "领涨股": "top_stock",
        "领涨股-涨跌幅": "top_stock_pct",
    }
    df = df.rename(columns=rename)
    df = df.sort_values("main_net", ascending=False)
    return df


def save_to_db(data_type, date, df):
    """存入 SQLite"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    if data_type == "industry":
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
                UNIQUE(date, name)
            )
        """)
        for _, r in df.iterrows():
            cur.execute("""
                INSERT OR REPLACE INTO board_industry
                (date, name, close, change_pct, inflow, outflow, main_net, company_count, top_stock, top_stock_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, r["name"], r.get("close", 0), r.get("change_pct", 0),
                  r.get("inflow", 0), r.get("outflow", 0), r.get("main_net", 0),
                  r.get("company_count", 0), r.get("top_stock", ""), r.get("top_stock_pct", 0)))

    elif data_type == "fund_flow":
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
                UNIQUE(date, name)
            )
        """)
        for _, r in df.iterrows():
            cur.execute("""
                INSERT OR REPLACE INTO board_fund_flow
                (date, name, close, change_pct, inflow, outflow, main_net, company_count, top_stock, top_stock_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, r["name"], r.get("close", 0), r.get("change_pct", 0),
                  r.get("inflow", 0), r.get("outflow", 0), r.get("main_net", 0),
                  r.get("company_count", 0), r.get("top_stock", ""), r.get("top_stock_pct", 0)))

    conn.commit()
    conn.close()


def fmt_net(v):
    """格式化资金净额（假设原始数据单位=亿元）"""
    if v == 0:
        return " 0 "
    if abs(v) >= 1:
        return f"{v:+.1f}亿"
    # 小于1亿用万显示
    return f"{v*10000:+.0f}万"


def print_report(date, industry_df, fund_df):
    print(f"\n{'='*60}")
    print(f"📅 {date}  板块数据")
    print(f"{'='*60}")

    # ========== 行业板块 ==========
    if not industry_df.empty:
        ind_top5 = industry_df.head(5)
        ind_bot5 = industry_df.tail(5).iloc[::-1]

        print(f"\n📈 行业板块涨幅 TOP5（{len(industry_df)}个板块）")
        print(f"  {'板块':<14} {'涨跌幅':>8} {'主力净流入':>12} {'领涨股':<10} {'领涨股涨幅':>8}")
        print(f"  {'-'*58}")
        for _, r in ind_top5.iterrows():
            arrow = "▲" if r["change_pct"] >= 0 else "▼"
            print(f"  {r['name']:<12} {arrow}{r['change_pct']:>+6.2f}% {fmt_net(r.get('main_net',0)):>10}   {r.get('top_stock',''):<8} {r.get('top_stock_pct',0):>+7.2f}%")

        print(f"\n📉 行业板块跌幅 TOP5")
        print(f"  {'板块':<14} {'涨跌幅':>8} {'主力净流入':>12} {'领涨股':<10} {'领涨股涨幅':>8}")
        print(f"  {'-'*58}")
        for _, r in ind_bot5.iterrows():
            arrow = "▲" if r["change_pct"] >= 0 else "▼"
            print(f"  {r['name']:<12} {arrow}{r['change_pct']:>+6.2f}% {fmt_net(r.get('main_net',0)):>10}   {r.get('top_stock',''):<8} {r.get('top_stock_pct',0):>+7.2f}%")

        # 行业主力净流入 Top5
        ind_by_net = industry_df.sort_values("main_net", ascending=False).head(5)
        print(f"\n💰 行业板块主力净流入 TOP5")
        print(f"  {'板块':<14} {'主力净流入':>12} {'涨幅':>8} {'流入':>10} {'流出':>10}")
        print(f"  {'-'*58}")
        for _, r in ind_by_net.iterrows():
            arrow = "▲" if r["change_pct"] >= 0 else "▼"
            print(f"  {r['name']:<12} {fmt_net(r.get('main_net',0)):>10} {arrow}{r['change_pct']:>+6.2f}% {r.get('inflow',0):>8.1f}亿 {r.get('outflow',0):>8.1f}亿")

    # ========== 概念板块 ==========
    if not fund_df.empty:
        concept_top5 = fund_df.head(5)
        concept_net_top5 = fund_df.sort_values("main_net", ascending=False).head(5)
        concept_net_bot5 = fund_df.sort_values("main_net", ascending=True).head(5)

        print(f"\n{'='*60}")
        print(f"📈 概念板块涨幅 TOP5（{len(fund_df)}个概念）")
        print(f"  {'概念':<16} {'涨跌幅':>8} {'主力净流入':>12} {'领涨股':<10} {'领涨股涨幅':>8}")
        print(f"  {'-'*60}")
        for _, r in concept_top5.iterrows():
            arrow = "▲" if r["change_pct"] >= 0 else "▼"
            print(f"  {r['name']:<14} {arrow}{r['change_pct']:>+6.2f}% {fmt_net(r.get('main_net',0)):>10}   {r.get('top_stock',''):<8} {r.get('top_stock_pct',0):>+7.2f}%")

        print(f"\n💰 概念板块主力净流入 TOP5")
        print(f"  {'概念':<16} {'主力净流入':>12} {'涨幅':>8} {'领涨股':<10}")
        print(f"  {'-'*50}")
        for _, r in concept_net_top5.iterrows():
            arrow = "▲" if r["change_pct"] >= 0 else "▼"
            print(f"  {r['name']:<14} {fmt_net(r.get('main_net',0)):>10} {arrow}{r['change_pct']:>+6.2f}%  {r.get('top_stock',''):<8}")

        print(f"\n💸 概念板块主力净流出 TOP5")
        print(f"  {'概念':<16} {'主力净流出':>12} {'跌幅':>8} {'领涨股':<10}")
        print(f"  {'-'*50}")
        for _, r in concept_net_bot5.iterrows():
            arrow = "▲" if r["change_pct"] >= 0 else "▼"
            print(f"  {r['name']:<14} {fmt_net(r.get('main_net',0)):>10} {arrow}{r['change_pct']:>+6.2f}%  {r.get('top_stock',''):<8}")


def main():
    args = sys.argv
    if len(args) < 2:
        # 默认昨天
        date = (datetime.now() - pd.Timedelta(days=1)).strftime("%Y%m%d")
    else:
        date = args[1]
    date_display = f"{date[:4]}-{date[4:6]}-{date[6:]}"

    print(f"📡 拉取板块数据: {date_display}")

    try:
        ind_df = get_board_industry()
        print(f"  板块行情: {len(ind_df)}个板块")
    except Exception as e:
        print(f"  ❌ 板块行情失败: {e}")
        ind_df = pd.DataFrame()

    try:
        flow_df = get_sector_fund_flow()
        print(f"  资金流: {len(flow_df)}个板块")
    except Exception as e:
        print(f"  ❌ 资金流失败: {e}")
        flow_df = pd.DataFrame()

    if ind_df.empty and flow_df.empty:
        print("❌ 两个数据源都失败了")
        return

    # 存入DB
    if not ind_df.empty:
        save_to_db("industry", date_display, ind_df)
        print(f"  ✅ 板块行情已存库")
    if not flow_df.empty:
        save_to_db("fund_flow", date_display, flow_df)
        print(f"  ✅ 资金流已存库")

    # 打印报告
    if not ind_df.empty:
        print_report(date_display, ind_df, flow_df)


if __name__ == "__main__":
    main()
