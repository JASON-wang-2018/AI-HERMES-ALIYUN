#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票技术分析模块
K线 / 量价关系 / 技术指标 / 趋势波段 / 主力行为
Author: 纳福 for Jason
"""

import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.expanduser("~/stock_knowledge")
DB_PATH = os.path.join(BASE_DIR, "database/stock_data.db")

# ===================== 数据加载 =====================

def load_kline(stock_code, days=120):
    """加载日K线数据"""
    conn = sqlite3.connect(DB_PATH)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql(
        f"SELECT * FROM daily_kline WHERE stock_code=? AND trade_date>=? ORDER BY trade_date",
        conn, params=(stock_code, cutoff)
    )
    conn.close()
    if df.empty:
        return None
    # 数值化
    for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# ===================== K线分析 =====================

def detect_kline_type(row):
    """识别单根K线类型"""
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    avg_body = body if body > 0 else 0.01

    ktype = "other"
    if body < (h - l) * 0.1:
        ktype = "十字星"
    elif upper_shadow > body * 2 and lower_shadow < body * 0.3:
        ktype = "锤子线" if c > o else "吊颈线"
    elif upper_shadow < body * 0.3 and lower_shadow > body * 2:
        ktype = "倒锤线" if c > o else "墓碑线"
    elif c > o and upper_shadow < body * 0.3 and lower_shadow < body * 0.3:
        ktype = "光头光脚阳"
    elif c < o and upper_shadow < body * 0.3 and lower_shadow < body * 0.3:
        ktype = "光头光脚阴"
    elif c > o:
        ktype = "阳线"
    else:
        ktype = "阴线"
    return ktype

def detect_kline_patterns(df):
    """识别K线组合形态"""
    if df is None or len(df) < 3:
        return []
    patterns = []
    for i in range(2, len(df)):
        c3 = df.iloc[i-2:i+1]
        # 吞没形态
        if (c3.iloc[0]["close"] < c3.iloc[0]["open"] and
            c3.iloc[1]["close"] < c3.iloc[1]["open"] and
            c3.iloc[2]["close"] > c3.iloc[2]["open"] and
            c3.iloc[2]["close"] > c3.iloc[0]["open"] and
            c3.iloc[2]["open"] < c3.iloc[0]["close"]):
            patterns.append(f"{c3.iloc[2]['trade_date']}: 底部吞没（看涨）")
        if (c3.iloc[0]["close"] > c3.iloc[0]["open"] and
            c3.iloc[1]["close"] > c3.iloc[1]["open"] and
            c3.iloc[2]["close"] < c3.iloc[2]["open"] and
            c3.iloc[2]["close"] < c3.iloc[0]["open"] and
            c3.iloc[2]["open"] > c3.iloc[0]["close"]):
            patterns.append(f"{c3.iloc[2]['trade_date']}: 顶部吞没（看跌）")
        # 红三兵
        if (c3.iloc[0]["close"] > c3.iloc[0]["open"] and
            c3.iloc[1]["close"] > c3.iloc[1]["open"] and
            c3.iloc[2]["close"] > c3.iloc[2]["open"] and
            c3.iloc[0]["close"] < c3.iloc[1]["close"] and
            c3.iloc[1]["close"] < c3.iloc[2]["close"]):
            patterns.append(f"{c3.iloc[2]['trade_date']}: 红三兵（看涨）")
    return patterns[-5:]  # 只返回最近5个

# ===================== 量价关系 =====================

def analyze_volume_price(df):
    """量价综合分析"""
    if df is None or len(df) < 5:
        return {}
    result = {}
    df = df.tail(20)  # 看最近20天
    # 计算量比
    avg_vol5 = df["volume"].rolling(5).mean()
    avg_vol10 = df["volume"].rolling(10).mean()
    vol_ratio = df["volume"].iloc[-1] / avg_vol5.iloc[-1] if avg_vol5.iloc[-1] > 0 else 0
    result["量比"] = round(vol_ratio, 2)
    # 放量/缩量判断
    if vol_ratio > 1.5:
        result["量能状态"] = "明显放量"
    elif vol_ratio > 1.1:
        result["量能状态"] = "温和放量"
    elif vol_ratio < 0.5:
        result["量能状态"] = "明显缩量"
    elif vol_ratio < 0.8:
        result["量能状态"] = "温和缩量"
    else:
        result["量能状态"] = "量能正常"
    # 量价背离
    price_trend = df["close"].iloc[-1] - df["close"].iloc[-5]
    vol_trend = df["volume"].iloc[-1] - df["volume"].iloc[-5]
    if price_trend > 0 and vol_trend < 0:
        result["量价背离"] = "价涨量缩（警惕）"
    elif price_trend < 0 and vol_trend > 0:
        result["量价背离"] = "价跌量增（警惕）"
    else:
        result["量价背离"] = "量价配合正常"
    # 换手率
    result["换手率"] = round(df["turnover"].iloc[-1], 2) if "turnover" in df.columns else 0
    return result

# ===================== 均线系统 =====================

def calc_ma(df, periods=[5, 10, 20, 60, 120, 250]):
    """计算均线"""
    if df is None:
        return df
    for p in periods:
        if f"ma{p}" not in df.columns:
            df[f"ma{p}"] = df["close"].rolling(p).mean()
    return df

def ma_signals(df):
    """均线信号"""
    if df is None or len(df) < 60:
        return []
    signals = []
    ma5 = df["ma5"].iloc[-1]
    ma10 = df["ma10"].iloc[-1]
    ma20 = df["ma20"].iloc[-1]
    ma60 = df["ma60"].iloc[-1]
    c = df["close"].iloc[-1]
    # 多头排列
    if ma5 > ma10 > ma20 > ma60:
        signals.append("均线多头排列（强势）")
    # 空头排列
    if ma5 < ma10 < ma20 < ma60:
        signals.append("均线空头排列（弱势）")
    # 均线金叉
    if ma5 > ma10 and df["ma5"].iloc[-2] <= df["ma10"].iloc[-2]:
        signals.append("MA5上穿MA10（金叉）")
    # 均线死叉
    if ma5 < ma10 and df["ma5"].iloc[-2] >= df["ma10"].iloc[-2]:
        signals.append("MA5下穿MA10（死叉）")
    # 价格与均线
    if c > ma60:
        signals.append("股价在60日线上方")
    else:
        signals.append("股价在60日线下方")
    return signals

# ===================== MACD =====================

def calc_macd(df, fast=12, slow=26, signal=9):
    """MACD指标"""
    if df is None or "close" not in df.columns:
        return df
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    df["dif"] = dif
    df["dea"] = dea
    df["macd"] = macd
    return df

def macd_signals(df):
    """MACD信号"""
    if df is None or "macd" not in df.columns or len(df) < 3:
        return []
    signals = []
    dif = df["dif"].iloc[-1]
    dea = df["dea"].iloc[-1]
    macd = df["macd"].iloc[-1]
    dif_prev = df["dif"].iloc[-2]
    dea_prev = df["dea"].iloc[-2]
    # 金叉
    if dif > dea and dif_prev <= dea_prev:
        signals.append("MACD金叉")
    # 死叉
    if dif < dea and dif_prev >= dea_prev:
        signals.append("MACD死叉")
    # 顶背离
    if df["close"].iloc[-1] > df["close"].iloc[-5] and dif < dif_prev:
        signals.append("MACD顶背离（警惕）")
    # 底背离
    if df["close"].iloc[-1] < df["close"].iloc[-5] and dif > dif_prev:
        signals.append("MACD底背离（关注）")
    # 柱状体收缩
    if abs(macd) < abs(df["macd"].iloc[-2]):
        signals.append("MACD柱收缩（可能变盘）")
    return signals

# ===================== KDJ =====================

def calc_kdj(df, n=9, m1=3, m2=3):
    """KDJ指标"""
    if df is None or "close" not in df.columns:
        return df
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    df["K"] = rsv.ewm(com=m1-1, adjust=False).mean()
    df["D"] = df["K"].ewm(com=m2-1, adjust=False).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    return df

def kdj_signals(df):
    """KDJ信号"""
    if df is None or "K" not in df.columns:
        return []
    signals = []
    k = df["K"].iloc[-1]
    d = df["D"].iloc[-1]
    j = df["J"].iloc[-1]
    if k > 80:
        signals.append("KDJ 超买区域")
    if k < 20:
        signals.append("KDJ 超卖区域")
    if k > d and df["K"].iloc[-2] <= df["D"].iloc[-2]:
        signals.append("KDJ 金叉")
    if k < d and df["K"].iloc[-2] >= df["D"].iloc[-2]:
        signals.append("KDJ 死叉")
    if j > 100:
        signals.append("KDJ J值过高（警惕）")
    if j < 0:
        signals.append("KDJ J值过低（关注）")
    return signals

# ===================== RSI =====================

def calc_rsi(df, periods=[6, 12, 24]):
    """RSI指标"""
    if df is None or "close" not in df.columns:
        return df
    for p in periods:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/p, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/p, adjust=False).mean()
        rs = gain / loss
        df[f"rsi{p}"] = 100 - (100 / (1 + rs))
    return df

def rsi_signals(df):
    """RSI信号"""
    if df is None or "rsi6" not in df.columns:
        return []
    signals = []
    rsi6 = df["rsi6"].iloc[-1]
    rsi12 = df["rsi12"].iloc[-1]
    if rsi6 > 80:
        signals.append("RSI6 超买")
    if rsi6 < 20:
        signals.append("RSI6 超卖")
    if rsi6 > rsi12 and df["rsi6"].iloc[-2] <= df["rsi12"].iloc[-2]:
        signals.append("RSI 短线上穿长线")
    if rsi6 < rsi12 and df["rsi6"].iloc[-2] >= df["rsi12"].iloc[-2]:
        signals.append("RSI 短线跌破长线")
    return signals

# ===================== 布林带 =====================

def calc_boll(df, period=20, std_dev=2):
    """布林带"""
    if df is None or "close" not in df.columns:
        return df
    df["boll_mid"] = df["close"].rolling(period).mean()
    df["boll_std"] = df["close"].rolling(period).std()
    df["boll_upper"] = df["boll_mid"] + std_dev * df["boll_std"]
    df["boll_lower"] = df["boll_mid"] - std_dev * df["boll_std"]
    return df

def boll_signals(df):
    """布林带信号"""
    if df is None or "boll_upper" not in df.columns:
        return []
    signals = []
    c = df["close"].iloc[-1]
    upper = df["boll_upper"].iloc[-1]
    lower = df["boll_lower"].iloc[-1]
    mid = df["boll_mid"].iloc[-1]
    if c > upper:
        signals.append("价格突破布林上轨（超买信号）")
    if c < lower:
        signals.append("价格跌破布林下轨（超卖信号）")
    if c < lower and df["volume"].iloc[-1] > df["volume"].rolling(5).mean().iloc[-1]:
        signals.append("布林下轨 + 放量（关注买点）")
    return signals

# ===================== 趋势波段分析 =====================

def detect_price_position(df):
    """价格位置分析"""
    if df is None or len(df) < 60:
        return {}
    c = df["close"].iloc[-1]
    high60 = df["high"].rolling(60).max().iloc[-1]
    low60 = df["low"].rolling(60).min().iloc[-1]
    high120 = df["high"].rolling(120).max().iloc[-1]
    low120 = df["low"].rolling(120).min().iloc[-1]
    position_60 = (c - low60) / (high60 - low60) * 100 if high60 != low60 else 50
    position_120 = (c - low120) / (high120 - low120) * 100 if high120 != low120 else 50
    return {
        "价格位置(60日)": f"{position_60:.1f}%",
        "价格位置(120日)": f"{position_120:.1f}%",
        "60日高点距离": f"{(high60-c)/c*100:.1f}%",
        "60日低点距离": f"{(c-low60)/c*100:.1f}%"
    }

def detect_wave_bands(df):
    """波段分析（简单版本）"""
    if df is None or len(df) < 20:
        return {}
    close = df["close"]
    # 使用高低点追踪简化版本
    high20 = df["high"].rolling(20).max()
    low20 = df["low"].rolling(20).min()
    atr = (df["high"] - df["low"]).rolling(10).mean()
    current_high = high20.iloc[-1]
    current_low = low20.iloc[-1]
    c = close.iloc[-1]
    # 波段判断
    if c > df["close"].iloc[-5] * 1.05:
        trend = "短期上升趋势"
    elif c < df["close"].iloc[-5] * 0.95:
        trend = "短期下降趋势"
    else:
        trend = "短期震荡"
    return {
        "短期趋势": trend,
        "20日区间": f"{current_low:.2f} ~ {current_high:.2f}",
        "ATR(波动率)": round(atr.iloc[-1], 2)
    }

# ===================== 综合分析报告 =====================

def full_analysis(stock_code):
    """生成综合分析报告"""
    print(f"\n{'='*60}")
    print(f"📊 个股综合分析: {stock_code}")
    print(f"{'='*60}")
    df = load_kline(stock_code)
    if df is None or df.empty:
        print("❌ 无数据")
        return
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_kdj(df)
    df = calc_rsi(df)
    df = calc_boll(df)
    # 基本信息
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    print(f"\n【基本信息】")
    print(f"  日期: {latest['trade_date']}  收盘: {latest['close']:.2f}")
    print(f"  涨跌: {(latest['close']/prev['close']-1)*100:+.2f}%")
    print(f"  开盘: {latest['open']:.2f}  最高: {latest['high']:.2f}  最低: {latest['low']:.2f}")
    print(f"  成交量: {latest['volume']/10000:.0f}万手  成交额: {latest['amount']/100000000:.2f}亿")
    # K线形态
    ktype = detect_kline_type(latest)
    print(f"\n【K线形态】  {ktype}")
    patterns = detect_kline_patterns(df)
    if patterns:
        for p in patterns:
            print(f"  📌 {p}")
    # 量价分析
    vp = analyze_volume_price(df)
    print(f"\n【量价分析】")
    for k, v in vp.items():
        print(f"  {k}: {v}")
    # 均线
    signals = ma_signals(df)
    if signals:
        print(f"\n【均线信号】")
        for s in signals:
            print(f"  → {s}")
    # MACD
    signals = macd_signals(df)
    if signals:
        print(f"\n【MACD信号】")
        for s in signals:
            print(f"  → {s}")
    # KDJ
    signals = kdj_signals(df)
    if signals:
        print(f"\n【KDJ信号】")
        for s in signals:
            print(f"  → {s}")
    # RSI
    signals = rsi_signals(df)
    if signals:
        print(f"\n【RSI信号】")
        for s in signals:
            print(f"  → {s}")
    # 布林带
    signals = boll_signals(df)
    if signals:
        print(f"\n【布林带信号】")
        for s in signals:
            print(f"  → {s}")
    # 趋势位置
    pos = detect_price_position(df)
    if pos:
        print(f"\n【价格位置】")
        for k, v in pos.items():
            print(f"  {k}: {v}")
    # 波段
    bands = detect_wave_bands(df)
    if bands:
        print(f"\n【波段分析】")
        for k, v in bands.items():
            print(f"  {k}: {v}")
    print(f"\n{'='*60}\n")

# ===================== 主程序 =====================

if __name__ == "__main__":
    # 演示：对数据库中的股票进行分析
    stocks = ["600519", "000858", "601318"]
    for code in stocks:
        full_analysis(code)
