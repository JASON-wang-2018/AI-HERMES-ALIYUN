#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国A股数据采集器
支持：AKShare / Baostock / Tushare
Author: 纳福 for Jason
"""

import pandas as pd
import numpy as np
import requests
import json
import time
import sqlite3
from datetime import datetime, timedelta
import os
import sys

# 路径配置
BASE_DIR = os.path.expanduser("~/stock_knowledge")
DB_PATH = os.path.join(BASE_DIR, "database/stock_data.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

def log(msg):
    """日志记录"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    with open(os.path.join(LOG_DIR, "data_fetch.log"), "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

# ===================== 数据源接口 =====================

def fetch_akshare_daily(stock_code, start_date, end_date):
    """AKShare 日K线数据"""
    try:
        import akshare as ak
        # 格式化代码：上证为 sh.000001，深证为 sz.000001
        if stock_code.startswith("6"):
            code = f"sh{stock_code}"
        else:
            code = f"sz{stock_code}"
        df = ak.stock_zh_a_hist(symbol=stock_code, start_date=start_date, end_date=end_date, adjust="qfq")
        return df
    except Exception as e:
        log(f"[AKShare ERROR] {stock_code}: {e}")
        return None

def fetch_baostock_daily(stock_code, start_date, end_date):
    """Baostock 日K线数据"""
    try:
        import baostock as bs
        bs.login()
        # baostock 代码格式: sh.600000
        if stock_code.startswith("6"):
            code = f"sh.{stock_code}"
        else:
            code = f"sz.{stock_code}"
        rs = bs.query_history_k_data_plus(
            code,
            "date,open,high,low,close,volume,amount,turn",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="2"  # 前复权
        )
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        bs.logout()
        if data_list:
            df = pd.DataFrame(data_list, columns=rs.fields)
            return df
        return None
    except Exception as e:
        log(f"[Baostock ERROR] {stock_code}: {e}")
        return None

def fetch_realtime_from_sina(stock_code):
    """新浪财经实时行情"""
    try:
        if stock_code.startswith("6"):
            symbol = f"sh{stock_code}"
        else:
            symbol = f"sz{stock_code}"
        url = f"https://hq.sinajs.cn/list={symbol}"
        headers = {"Referer": "https://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=5)
        text = resp.content.decode("gbk")
        # 格式: var hq_str_sh600001="名称,今开,昨收,当前价,最高,最低,...成交量..."
        content = text.split('"')[1]
        fields = content.split(',')
        if len(fields) > 30:
            return {
                "stock_code": stock_code,
                "name": fields[0],
                "open": float(fields[1]) if fields[1] else 0,
                "prev_close": float(fields[2]) if fields[2] else 0,
                "close": float(fields[3]) if fields[3] else 0,
                "high": float(fields[4]) if fields[4] else 0,
                "low": float(fields[5]) if fields[5] else 0,
                "volume": int(fields[8]) if fields[8] else 0,
                "amount": float(fields[9]) if fields[9] else 0,
                "update_time": fields[31] if len(fields) > 31 else "",
                "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        return None
    except Exception as e:
        log(f"[Sina Realtime ERROR] {stock_code}: {e}")
        return None

def fetch_realtime_from_eastmoney(stock_code):
    """东方财富实时行情（备用）"""
    try:
        if stock_code.startswith("6"):
            secid = f"1.{stock_code}"
        else:
            secid = f"0.{stock_code}"
        url = f"https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f170",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fltt": 2,
            "invt": 2
        }
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json().get("data", {})
        if data:
            return {
                "stock_code": stock_code,
                "name": data.get("f58", ""),
                "close": data.get("f43", 0) / 100 if data.get("f43") else 0,
                "open": data.get("f43", 0) / 100 if data.get("f43") else 0,  # 用最新价代替开盘
                "high": data.get("f44", 0) / 100 if data.get("f44") else 0,
                "low": data.get("f45", 0) / 100 if data.get("f45") else 0,
                "volume": data.get("f47", 0) if data.get("f47") else 0,
                "amount": data.get("f48", 0) if data.get("f48") else 0,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        return None
    except Exception as e:
        log(f"[EastMoney ERROR] {stock_code}: {e}")
        return None

# ===================== 数据校验 =====================

def validate_realtime_data(data):
    """实时数据校验"""
    if not data:
        return False, "数据为空"
    if data.get("close", 0) <= 0:
        return False, "价格<=0，无效"
    if data.get("high", 0) < data.get("low", 0):
        return False, "最高价<最低价，数据异常"
    if data.get("close", 0) > data.get("high", 0) * 1.5:
        return False, "收盘价异常偏高"
    if data.get("close", 0) < data.get("low", 0) * 0.5:
        return False, "收盘价异常偏低"
    return True, "OK"

# ===================== 数据库操作 =====================

def init_database():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_kline (
            stock_code TEXT,
            trade_date TEXT,
            open REAL, high REAL, low REAL, close REAL,
            volume INTEGER, amount REAL, turnover REAL,
            adjust_flag TEXT, source TEXT,
            fetch_time TEXT,
            PRIMARY KEY (stock_code, trade_date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS realtime_quote (
            stock_code TEXT PRIMARY KEY,
            name TEXT, open REAL, prev_close REAL,
            close REAL, high REAL, low REAL,
            volume INTEGER, amount REAL,
            update_time TEXT, fetch_time TEXT,
            source TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT, source TEXT,
            status TEXT, error_msg TEXT,
            fetch_time TEXT
        )
    """)
    conn.commit()
    conn.close()
    log(f"数据库初始化完成: {DB_PATH}")

def save_daily_kline(df, stock_code, source="akshare"):
    """保存日K线数据"""
    if df is None or df.empty:
        return
    conn = sqlite3.connect(DB_PATH)
    df = df.copy()
    # 统一字段名（AKShare用中文字段名）
    rename_map = {
        "日期": "trade_date",
        "股票代码": "stock_code",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "换手率": "turnover",
    }
    # 动态重命名
    cols = {c: c for c in df.columns}
    for ch, en in rename_map.items():
        if ch in df.columns:
            cols[ch] = en
    df = df.rename(columns=cols)
    # 只保留数据库需要的列
    db_cols = ["stock_code","trade_date","open","high","low","close","volume","amount","turnover","source","fetch_time"]
    available = [c for c in db_cols if c in df.columns]
    df = df[available]
    df["stock_code"] = stock_code
    df["source"] = source
    df["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.to_sql("daily_kline", conn, if_exists="append", index=False)
    conn.close()

def save_realtime_quote(data, source="sina"):
    """保存实时行情"""
    if not data:
        return
    conn = sqlite3.connect(DB_PATH)
    data["source"] = source
    df = pd.DataFrame([data])
    df.to_sql("realtime_quote", conn, if_exists="replace", index=False)
    conn.close()

def log_fetch(stock_code, source, status, error_msg=""):
    """记录采集日志"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO fetch_log (stock_code, source, status, error_msg, fetch_time)
        VALUES (?, ?, ?, ?, ?)
    """, (stock_code, source, status, error_msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ===================== 主程序 =====================

def get_stock_list():
    """获取股票列表（可扩展为从文件/数据库读取）"""
    # 默认演示：用主要指数成分股
    return {
        "600519": "贵州茅台",
        "000858": "五粮液",
        "601318": "中国平安",
        "600036": "招商银行",
        "000001": "平安银行",
        "002594": "比亚迪",
        "300750": "宁德时代",
        "688981": "中芯国际",
    }

def fetch_batch_realtime(stock_codes):
    """批量采集实时数据"""
    results = []
    for code, name in stock_codes.items():
        # 先用新浪
        data = fetch_realtime_from_sina(code)
        source = "sina"
        if not data:
            # 备用东方财富
            data = fetch_realtime_from_eastmoney(code)
            source = "eastmoney"
        if data:
            valid, msg = validate_realtime_data(data)
            if valid:
                save_realtime_quote(data, source)
                results.append(data)
                log(f"[{code}] {name}: 采集成功 ({source})")
            else:
                log(f"[{code}] {name}: 校验失败 - {msg}")
                log_fetch(code, source, "VALIDATION_FAILED", msg)
        else:
            log(f"[{code}] {name}: 采集失败")
            log_fetch(code, source, "FAILED", "No data returned")
        time.sleep(0.3)  # 避免请求过快
    return results

def fetch_historical_data(stock_code, start_date="20250101", end_date=None):
    """采集历史数据"""
    if not end_date:
        end_date = datetime.now().strftime("%Y%m%d")
    
    # 尝试AKShare
    df = fetch_akshare_daily(stock_code, start_date, end_date)
    if df is not None and not df.empty:
        save_daily_kline(df, stock_code, "akshare")
        log(f"[{stock_code}] A股历史数据采集成功: {len(df)} 条")
        return df
    
    # 备用Baostock
    df = fetch_baostock_daily(stock_code, start_date, end_date)
    if df is not None and not df.empty:
        save_daily_kline(df, stock_code, "baostock")
        log(f"[{stock_code}] Baostock历史数据采集成功: {len(df)} 条")
        return df
    
    log(f"[{stock_code}] 历史数据采集失败")
    return None

def main():
    log("=" * 50)
    log("A股数据采集器启动")
    init_database()
    
    stocks = get_stock_list()
    log(f"待采集股票数: {len(stocks)}")
    
    # 采集实时行情
    log("开始采集实时行情...")
    results = fetch_batch_realtime(stocks)
    log(f"实时行情采集完成: {len(results)}/{len(stocks)} 成功")
    
    # 采集历史数据（演示用）
    log("开始采集历史K线数据...")
    for code in list(stocks.keys())[:3]:  # 先演示3只
        fetch_historical_data(code)
    
    log("采集任务完成")

if __name__ == "__main__":
    main()
