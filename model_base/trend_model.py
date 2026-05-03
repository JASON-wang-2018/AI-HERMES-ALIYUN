#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趋势跟踪模型
基于均线系统 + MACD 的趋势判断
Author: 纳福 for Jason
"""

import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.expanduser("~/stock_knowledge")
DB_PATH = os.path.join(BASE_DIR, "database/stock_data.db")

def load_kline(stock_code, days=250):
    conn = sqlite3.connect(DB_PATH)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql(
        "SELECT * FROM daily_kline WHERE stock_code=? AND trade_date>=? ORDER BY trade_date",
        conn, params=(stock_code, cutoff)
    )
    conn.close()
    for col in ["open","high","low","close","volume","amount","turnover"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def calc_ma(close, periods=[5,10,20,60,120,250]):
    ma = {}
    for p in periods:
        ma[f"ma{p}"] = close.rolling(p).mean()
    return ma

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    return dif, dea, macd

class TrendModel:
    """趋势跟踪模型"""

    def __init__(self, stock_code):
        self.code = stock_code
        self.df = load_kline(stock_code)
        self.ma = None
        self.dif = None
        self.dea = None
        self.macd = None

    def compute(self):
        if self.df is None or self.df.empty:
            return
        close = self.df["close"]
        self.ma = calc_ma(close)
        self.dif, self.dea, self.macd = calc_macd(close)

    def trend_direction(self):
        """判断中长期趋势方向"""
        if self.ma is None:
            return "UNKNOWN"
        ma5 = self.ma["ma5"].iloc[-1]
        ma20 = self.ma["ma20"].iloc[-1]
        ma60 = self.ma["ma60"].iloc[-1]
        if pd.isna(ma5) or pd.isna(ma60):
            return "UNKNOWN"
        if ma5 > ma20 > ma60:
            return "上升趋势"
        elif ma5 < ma20 < ma60:
            return "下降趋势"
        else:
            return "震荡趋势"

    def short_term_bias(self):
        """短线偏多/偏空"""
        if self.ma is None:
            return "UNKNOWN"
        ma5 = self.ma["ma5"].iloc[-1]
        ma10 = self.ma["ma10"].iloc[-1]
        close = self.df["close"].iloc[-1]
        if close > ma5 > ma10:
            return "偏多"
        elif close < ma5 < ma10:
            return "偏空"
        else:
            return "中性"

    def macd_signal(self):
        """MACD信号"""
        if self.dif is None:
            return "UNKNOWN"
        dif = self.dif.iloc[-1]
        dea = self.dea.iloc[-1]
        dif_prev = self.dif.iloc[-2]
        if dif > dea and dif_prev <= self.dea.iloc[-2]:
            return "金叉"
        elif dif < dea and dif_prev >= self.dea.iloc[-2]:
            return "死叉"
        elif dif > dea:
            return "多头"
        else:
            return "空头"

    def trend_strength(self):
        """趋势强度 0-100"""
        if self.ma is None:
            return 50
        close = self.df["close"].iloc[-1]
        ma5 = self.ma["ma5"].iloc[-1]
        ma20 = self.ma["ma20"].iloc[-1]
        ma60 = self.ma["ma60"].iloc[-1]
        if pd.isna(ma60):
            return 50
        # 计算价格相对均线的位置
        score = 0
        if close > ma5: score += 20
        if close > ma20: score += 20
        if close > ma60: score += 20
        if ma5 > ma20: score += 20
        if ma20 > ma60: score += 20
        return score

    def report(self):
        """生成趋势报告"""
        self.compute()
        if self.df is None or self.df.empty:
            print(f"[{self.code}] 无数据")
            return
        close = self.df["close"].iloc[-1]
        prev_close = self.df["close"].iloc[-2] if len(self.df) > 1 else close
        change = (close/prev_close - 1) * 100
        trend = self.trend_direction()
        bias = self.short_term_bias()
        macd_sig = self.macd_signal()
        strength = self.trend_strength()
        trend_emoji = "📈" if trend == "上升趋势" else ("📉" if trend == "下降趋势" else "📊")
        bias_emoji = "🟢" if bias == "偏多" else ("🔴" if bias == "偏空" else "⚪")
        print(f"\n{'='*50}")
        print(f"{trend_emoji} 趋势模型: {self.code}")
        print(f"{'='*50}")
        print(f"  收盘: {close:.2f} ({change:+.2f}%)")
        print(f"  中期趋势: {trend}")
        print(f"  短线偏多: {bias} {bias_emoji}")
        print(f"  MACD信号: {macd_sig}")
        print(f"  趋势强度: {strength}/100")
        if self.ma is not None:
            print(f"  均线: MA5={self.ma['ma5'].iloc[-1]:.2f} MA20={self.ma['ma20'].iloc[-1]:.2f} MA60={self.ma['ma60'].iloc[-1]:.2f}")
        print(f"{'='*50}\n")
        return {
            "stock_code": self.code,
            "close": close,
            "change_pct": round(change, 2),
            "trend": trend,
            "short_bias": bias,
            "macd_signal": macd_sig,
            "trend_strength": strength,
            "ma5": round(self.ma["ma5"].iloc[-1], 2) if self.ma is not None else None,
            "ma20": round(self.ma["ma20"].iloc[-1], 2) if self.ma is not None else None,
            "ma60": round(self.ma["ma60"].iloc[-1], 2) if self.ma is not None else None,
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

if __name__ == "__main__":
    for code in ["600519", "000858", "601318"]:
        model = TrendModel(code)
        model.report()
