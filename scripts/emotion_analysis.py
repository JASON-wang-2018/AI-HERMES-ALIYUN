#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情绪周期识别程序 | 短线量化分析模型 第一层
功能：每日自动识别A股市场情绪周期（冰点/修复/主升/退潮）
数据来源：AKShare 东方财富

使用方式：
    python3 scripts/emotion_analysis.py
    python3 scripts/emotion_analysis.py 20260427  # 指定日期
"""

import akshare as ak
import pandas as pd
import sys
from datetime import datetime, timedelta


def get_emotion_data(date: str) -> dict:
    """
    获取指定日期的情绪数据
    date格式: YYYYMMDD
    """
    try:
        # 涨停板池
        zt = ak.stock_zt_pool_em(date=date)
        # 跌停板池
        dt = ak.stock_zt_pool_dtgc_em(date=date)
        # 炸板池
        zbgc = ak.stock_zt_pool_zbgc_em(date=date)
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        return {}

    # ========== 基础统计 ==========
    zt_count = len(zt)           # 涨停家数
    dt_count = len(dt)           # 跌停家数
    zbgc_count = len(zbgc)       # 炸板家数

    # 涨停/跌停比
    zt_dt_ratio = zt_count / dt_count if dt_count > 0 else float('inf')

    # 炸板率 = 炸板数 / (涨停数+炸板数)
    zbgc_rate = zbgc_count / (zt_count + zbgc_count) * 100 if zt_count > 0 else 0

    # 连板统计
    if len(zt) > 0:
        lianban_max = zt['连板数'].max()           # 最高连板
        lianban_4plus = (zt['连板数'] >= 4).sum()  # 4板及以上
        lianban_3plus = (zt['连板数'] >= 3).sum()   # 3板及以上
        lianban_2plus = (zt['连板数'] >= 2).sum()   # 2板及以上

        # 首板时间统计（越早封板=越强）
        zt['首次封板时间'] = zt['首次封板时间'].astype(str)
        zb_time = zt[zt['首次封板时间'].str.len() == 6]
        early_zb = (zb_time['首次封板时间'] <= '0930').sum()  # 9:30前封板
        mid_zb = (zb_time['首次封板时间'] <= '1000').sum()    # 10:00前封板
    else:
        lianban_max = lianban_4plus = lianban_3plus = lianban_2plus = 0
        early_zb = mid_zb = 0

    # ========== 题材分布（Top5）==========
    if len(zt) > 0:
        sector_count = zt['所属行业'].value_counts().head(5)
        top_sectors = [(s, c) for s, c in sector_count.items()]
    else:
        top_sectors = []

    # ========== 龙头股（最高连板）==========
    if len(zt) > 0 and lianban_max >= 2:
        dragon = zt[zt['连板数'] == lianban_max].iloc[0]
        dragon_name = dragon['名称']
        dragon_code = dragon['代码']
        dragon_lians = int(dragon['连板数'])
        dragon_fengdan = dragon.get('封板资金', 'N/A')
        dragon_first_time = str(dragon.get('首次封板时间', 'N/A'))
    else:
        dragon_name = dragon_code = None
        dragon_lians = dragon_fengdan = dragon_first_time = None

    return {
        'date': date,
        'zt_count': zt_count,
        'dt_count': dt_count,
        'zbgc_count': zbgc_count,
        'zt_dt_ratio': zt_dt_ratio,
        'zbgc_rate': zbgc_rate,
        'lianban_max': lianban_max,
        'lianban_4plus': lianban_4plus,
        'lianban_3plus': lianban_3plus,
        'lianban_2plus': lianban_2plus,
        'early_zb': early_zb,
        'mid_zb': mid_zb,
        'top_sectors': top_sectors,
        'dragon_name': dragon_name,
        'dragon_code': dragon_code,
        'dragon_lians': dragon_lians,
        'dragon_fengdan': dragon_fengdan,
        'dragon_first_time': dragon_first_time,
    }


def judge_emotion_cycle(data: dict) -> tuple:
    """
    判断情绪周期阶段

    返回: (阶段名称, 量化得分, 操作策略)
    """
    if not data:
        return "数据获取失败", 0, "无法判断"

    zt = data['zt_count']
    dt = data['dt_count']
    zbgc_r = data['zbgc_rate']
    lianban = data['lianban_max']
    lianban_4plus = data['lianban_4plus']
    ratio = data['zt_dt_ratio']

    # 量化打分（0-100）
    score = 0

    # 涨停数量得分（30分）
    if zt >= 100: score += 30
    elif zt >= 80: score += 25
    elif zt >= 60: score += 20
    elif zt >= 40: score += 15
    elif zt >= 30: score += 10
    elif zt >= 20: score += 5
    else: score += 0

    # 连板高度得分（30分）
    if lianban >= 7: score += 30
    elif lianban >= 5: score += 25
    elif lianban >= 4: score += 20
    elif lianban >= 3: score += 15
    elif lianban >= 2: score += 8
    else: score += 0

    # 炸板率得分（20分）
    if zbgc_r <= 15: score += 20
    elif zbgc_r <= 25: score += 15
    elif zbgc_r <= 40: score += 8
    else: score += 0

    # 龙头质量得分（20分）
    if lianban_4plus >= 3: score += 20
    elif lianban_4plus >= 2: score += 15
    elif lianban_4plus >= 1: score += 10
    elif data['lianban_3plus'] >= 1: score += 5
    else: score += 0

    # 涨跌停比修正（附加）
    if dt == 0: score += 5   # 无跌停=极端多头
    elif ratio >= 5: score += 3
    elif ratio < 1: score -= 5  # 跌停多于涨停=差

    # 阶段判定
    if lianban >= 4 and zt >= 80 and zbgc_r <= 25:
        phase = "🟢 主升"
        strategy = "重仓做多，主攻龙头，核心利润区"
        color = "GREEN"
    elif lianban >= 3 and zt >= 40 and zt >= dt * 2:
        phase = "🟡 修复"
        strategy = "轻仓试错，主攻首板和1进2"
        color = "YELLOW"
    elif zt < 30 or zbgc_r > 45 or (dt > zt * 1.5 and zt < 30):
        phase = "🔴 冰点"
        strategy = "空仓休息，只做极轻仓试错 or 休息"
        color = "RED"
    elif lianban >= 2 and zbgc_r > 35:
        phase = "🟠 退潮"
        strategy = "只做低位板（首板），快进快出"
        color = "ORANGE"
    else:
        phase = "⚪ 震荡"
        strategy = "半仓观望，等待方向明确"
        color = "GRAY"

    return phase, score, strategy, color


def format_report(data: dict, phase: str, score: int, strategy: str, color: str) -> str:
    """格式化输出报告"""

    # 封板资金格式化
    fengdan = data.get('dragon_fengdan', 'N/A')
    if isinstance(fengdan, (int, float)) and fengdan != 'N/A':
        fengdan_str = f"{fengdan/1e8:.1f}亿" if fengdan >= 1e8 else f"{fengdan/1e4:.0f}万"
    else:
        fengdan_str = str(fengdan)

    report = f"""
{'='*55}
📊 情绪周期日报 | {data['date']}
{'='*55}

【情绪周期判定】
  阶段: {phase}
  量化得分: {score}/100 ({color})

【核心指标】
  涨停家数:    {data['zt_count']:>5}    {'✅ 充足' if data['zt_count'] >= 40 else '⚠️ 不足'}
  跌停家数:    {data['dt_count']:>5}    {'✅ 良好' if data['dt_count'] <= 10 else '⚠️ 偏多'}
  涨停/跌停比: {data['zt_dt_ratio']:>5.1f}x  {'✅ 多头' if data['zt_dt_ratio'] >= 2 else '⚠️ 空头'}
  炸板率:      {data['zbgc_rate']:>5.1f}%   {'✅ 低' if data['zbgc_rate'] <= 25 else '⚠️ 高'}

【连板高度】
  最高连板:    {data['lianban_max']}板
  4板+家数:    {data['lianban_4plus']:>5}    {'🔥 强' if data['lianban_4plus'] >= 2 else '➖ 一般'}
  3板+家数:    {data['lianban_3plus']:>5}
  2板+家数:    {data['lianban_2plus']:>5}
  9:30前封板:  {data['early_zb']:>5}家    {'🔥 强' if data['early_zb'] >= 5 else '➖ 一般'}

{'='*55}
【龙头股】
  名称:   {data['dragon_name'] if data['dragon_name'] else '无'}
  代码:   {data['dragon_code'] if data['dragon_code'] else '—'}
  连板:   {data['dragon_lians'] if data['dragon_lians'] else 0}板
  封单:   {fengdan_str}
  首封时间: {data['dragon_first_time'] if data['dragon_first_time'] else 'N/A'}

{'='*55}
【操作策略】
  {strategy}

【题材分布 Top5】
"""
    for i, (sector, count) in enumerate(data['top_sectors'], 1):
        report += f"  {i}. {sector}: {count}家\n"

    report += f"""
{'='*55}
【阶段量化标准参考】
  主升: 涨停≥80 + 连板≥4板 + 炸板率<25%
  修复: 涨停40~80 + 连板2~3板 + 涨停>跌停2倍
  冰点: 涨停<30 or 炸板率>45% or 跌停>涨停1.5倍
  退潮: 连板≥2板 + 炸板率>35% + 高位股杀跌

⚠️ 注意：五一假期前最后2个交易日（4/28-4/29）
   历史规律节前资金避险为主，建议降低仓位
{'='*55}
"""
    return report


def main():
    # 获取日期参数
    if len(sys.argv) >= 2:
        date = sys.argv[1]
    else:
        # 默认昨天（收盘后）
        yesterday = datetime.now() - timedelta(days=1)
        date = yesterday.strftime("%Y%m%d")

    print(f"\n📡 正在拉取 {date} 情绪数据...")

    data = get_emotion_data(date)

    if not data:
        print("❌ 数据获取失败，退出")
        return

    phase, score, strategy, color = judge_emotion_cycle(data)
    report = format_report(data, phase, score, strategy, color)
    print(report)


if __name__ == "__main__":
    main()
