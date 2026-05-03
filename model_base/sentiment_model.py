#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情绪周期模型
基于涨跌停数量、昨日涨停表现、龙虎榜等量化情绪
Author: 纳福 for Jason
"""

import sqlite3
import os
import pandas as pd
from datetime import datetime, timedelta

BASE_DIR = os.path.expanduser("~/stock_knowledge")
DB_PATH = os.path.join(BASE_DIR, "database/stock_data.db")

class MarketSentimentModel:
    """
    市场情绪量化模型
    核心指标：
    - 涨跌停数量
    - 昨日涨停今日表现
    - 炸板率
    - 高度板数量（连板）
    """

    def __init__(self):
        self.zt_count = 0       # 涨停家数
        self.dt_count = 0       # 跌停家数
        self.yz涨停涨幅 = 0       # 昨日涨停股今日平均涨幅
        self.zhaban_rate = 0     # 炸板率
        self.high_board = 0      # 3板以上数量
        self.score = 50          # 情绪综合评分 0-100
        self.level = "未知"      # 情绪等级

    def load_realtime(self):
        """从实时行情表加载情绪数据"""
        conn = sqlite3.connect(DB_PATH)
        try:
            df = pd.read_sql("SELECT * FROM realtime_quote", conn)
            conn.close()
            if df is None or df.empty:
                return
            # 简化版情绪评估（基于现有数据）
            # 完整实现需要专门的涨跌停数据表
            return df
        except:
            conn.close()
            return None

    def assess_yesterday_zt_performance(self):
        """
        评估昨日涨停股今日表现
        逻辑：
        - 若平均涨幅>5%，情绪高涨
        - 若平均涨幅<2%，情绪一般
        - 若平均涨幅<0，情绪差
        """
        # TODO: 需要历史涨停数据表支持
        pass

    def calc_score(self):
        """计算情绪综合评分"""
        # 简化评分逻辑（待数据丰富后完善）
        score = 50
        # 涨停家数加分
        if self.zt_count > 50:
            score += 15
        elif self.zt_count > 30:
            score += 10
        elif self.zt_count > 10:
            score += 5
        # 跌停家数减分
        if self.dt_count > 30:
            score -= 20
        elif self.dt_count > 10:
            score -= 10
        # 连板股加分
        score += min(self.high_board * 2, 10)
        # 炸板率减分
        score -= int(self.zhaban_rate * 0.3)
        self.score = max(0, min(100, score))
        # 情绪等级
        if self.score >= 80:
            self.level = "极度狂热 🔥🔥🔥"
        elif self.score >= 65:
            self.level = "情绪高涨 📈"
        elif self.score >= 55:
            self.level = "偏暖 📊"
        elif self.score >= 45:
            self.level = "中性 ⚖️"
        elif self.score >= 30:
            self.level = "偏冷 📉"
        else:
            self.level = "恐慌 🔥"

    def report(self):
        self.calc_score()
        print(f"\n{'='*50}")
        print(f"🌡️ 市场情绪分析")
        print(f"{'='*50}")
        print(f"  涨停家数: {self.zt_count}")
        print(f"  跌停家数: {self.dt_count}")
        print(f"  3板+数量: {self.high_board}")
        print(f"  炸板率: {self.zhaban_rate}%")
        print(f"  ─────────────────")
        print(f"  情绪评分: {self.score}/100")
        print(f"  情绪等级: {self.level}")
        print(f"{'='*50}\n")
        return {
            "zt_count": self.zt_count,
            "dt_count": self.dt_count,
            "high_board": self.high_board,
            "zhaban_rate": self.zhaban_rate,
            "sentiment_score": self.score,
            "sentiment_level": self.level,
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

if __name__ == "__main__":
    model = MarketSentimentModel()
    model.zt_count = 35
    model.dt_count = 8
    model.high_board = 5
    model.zhaban_rate = 25
    model.report()
