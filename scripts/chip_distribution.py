#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CYQ筹码分布计算模块
基于 myhhub/stock 的 CYQCalculator 算法改造

算法原理：
1. 把 [minprice, maxprice] 价格区间分成 accuracy_factor 个刻度（默认150个）
2. 每根K线按换手率将筹码以"三角形分布"分配到 [low, high] 区间
   - 顶点 = 均价 = (open+close+high+low)/4
   - 三角形上半部：(curprice - low) / (avg - low) * G
   - 三角形下半部：(high - curprice) / (high - avg) * G
3. 每次分配后，历史筹码乘以 (1 - turnover_rate) 做时间衰减
4. 一字板（high==low）：矩形面积 = 三角形 × 2
5. 最终输出：获利比例、平均成本、90%/70%筹码集中区间

输入DataFrame列：open, close, high, low, turnover（换手率%，如 1.46 表示1.46%）
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Tuple, Dict, Optional


@dataclass
class ChipData:
    """筹码分布结果"""
    # 筹码堆叠数组（每个价格位的筹码量）
    x: np.ndarray
    # 价格分布数组（价格刻度，元）
    y: np.ndarray
    # 当前价格获利比例（0~1）
    benefit_part: float
    # 平均成本（50%分位成本，元）
    avg_cost: float
    # 90%筹码区间 {'priceRange': ['7.20', '6.50'], 'concentration': 0.051}
    # 70%筹码区间 同上
    percent_chips: Dict[str, Dict]
    # 盈亏分界下标
    boundary_idx: int
    # 交易天数
    trading_days: int
    # 日期
    date: str


def calc_chip_distribution(
    df: pd.DataFrame,
    accuracy_factor: int = 150,
    trading_days: int = 210,
    target_date: Optional[str] = None
) -> ChipData:
    """
    计算指定日期的筹码分布

    :param df: K线数据，含 open/close/high/low/turnover 列，按日期升序
    :param accuracy_factor: 精度因子（价格刻度数），越大越精细，默认150
    :param trading_days: 计算筹码分布的交易天数，默认210日（约1年）
    :param target_date: 目标日期，默认取最后一条。不在DataFrame中时取最近的前一个交易日
    :return: ChipData 对象
    """
    # --- 1. 确定截止索引，取最近 trading_days 日数据 ---
    if target_date is not None:
        # 找到 <= target_date 的最后一条
        mask = df['date'] <= target_date if 'date' in df.columns else df.index <= target_date
        df = df[mask]
        if df.empty:
            raise ValueError(f"没有找到 <= {target_date} 的数据")

    df = df.tail(trading_days).copy()
    if len(df) < 10:
        raise ValueError(f"有效数据不足10条，仅有{len(df)}条")

    # --- 2. 确定价格区间 ---
    maxprice = float(df['high'].max())
    minprice = float(df['low'].min())
    accuracy = max(0.01, (maxprice - minprice) / (accuracy_factor - 1))

    # 价格刻度数组
    y = np.array([round(minprice + accuracy * i, 2) for i in range(accuracy_factor)])
    x = np.zeros(accuracy_factor, dtype=np.float64)

    # 当前价（取最后一条）
    current_price = float(df.iloc[-1]['close'])
    current_date = str(df.iloc[-1]['date']) if 'date' in df.columns else str(df.index[-1])

    # 找当前价在y中的下标（盈亏分界）
    boundary_idx = 0
    for i, p in enumerate(y):
        if p >= current_price:
            boundary_idx = i
            break

    # --- 3. 逐日分配筹码（时间衰减模型）---
    for _, row in df.iterrows():
        open_p = float(row['open'])
        close = float(row['close'])
        high = float(row['high'])
        low = float(row['low'])
        turnover = float(row.get('turnover', 0))  # 换手率%，如1.46

        avg = (open_p + close + high + low) / 4.0
        turnover_rate = min(1.0, turnover / 100.0)  # 归一化到[0,1]

        # 历史筹码时间衰减
        x = x * (1 - turnover_rate)

        H_idx = int((high - minprice) / accuracy)
        L_idx = min(accuracy_factor - 1, int((low - minprice) / accuracy + 0.99))

        if high == low:
            # --- 一字板：矩形面积 = 三角形×2 ---
            G_point = accuracy_factor - 1
            x[G_point] += G_point * turnover_rate / 2.0
        else:
            # G = 2 / (high - low)，归一化系数
            G = 2.0 / (high - low)
            for j in range(L_idx, min(H_idx + 1, accuracy_factor)):
                cur_price = minprice + accuracy * j
                if cur_price <= avg:
                    # 上半三角
                    if abs(avg - low) < 1e-8:
                        x[j] += G * turnover_rate
                    else:
                        x[j] += (cur_price - low) / (avg - low) * G * turnover_rate
                else:
                    # 下半三角
                    if abs(high - avg) < 1e-8:
                        x[j] += G * turnover_rate
                    else:
                        x[j] += (high - cur_price) / (high - avg) * G * turnover_rate

    # --- 4. 归一化 ---
    total_chips = sum(float(f"{v:.12g}") for v in x)
    if total_chips > 0:
        x = x / total_chips  # 转为比例

    # --- 5. 辅助函数：给定筹码比例，找对应价格 ---
    def get_cost_by_chip(chip_ratio: float) -> float:
        """给定筹码占比（0~1），返回对应价格"""
        if chip_ratio <= 0:
            return minprice
        if chip_ratio >= 1:
            return maxprice
        cumsum = 0.0
        for i, v in enumerate(x):
            v_val = float(f"{v:.12g}")
            if cumsum + v_val >= chip_ratio:
                return round(minprice + i * accuracy, 2)
            cumsum += v_val
        return maxprice

    # --- 6. 计算各项指标 ---
    # 获利比例：当前价以下的筹码占比
    below_idx = boundary_idx
    _bene_sum = sum(float(f"{x[i]:.12g}") for i in range(below_idx + 1))
    benefit_part = float(f"{_bene_sum:.4f}")

    # 平均成本（50%分位）
    avg_cost = get_cost_by_chip(0.5)

    # 90% / 70% 筹码集中区间
    def percent_chips_calc(pct: float) -> Dict:
        lower_ratio = (1 - pct) / 2
        upper_ratio = (1 + pct) / 2
        p_low = get_cost_by_chip(lower_ratio)
        p_high = get_cost_by_chip(upper_ratio)
        concentration = 0.0 if (p_low + p_high) == 0 else (p_high - p_low) / (p_low + p_high)
        return {
            "priceRange": [f"{p_low:.2f}", f"{p_high:.2f}"],
            "concentration": round(concentration, 4)
        }

    percent_chips = {
        "90": percent_chips_calc(0.9),
        "70": percent_chips_calc(0.7),
    }

    return ChipData(
        x=x,
        y=y,
        benefit_part=round(benefit_part, 4),
        avg_cost=avg_cost,
        percent_chips=percent_chips,
        boundary_idx=boundary_idx,
        trading_days=len(df),
        date=current_date,
    )


def chip_analysis_text(chip: ChipData, stock_code: str = "", close_price: float = 0) -> str:
    """返回筹码分布分析段落文字（用于直接嵌入分析报告）"""
    lines = []
    lines.append(f"**⑩筹码分布（CYC成本）**：")
    lines.append(f"  • 获利比例：{chip.benefit_part:.1%}（{chip.benefit_part - 0.5:.1%}高于成本线）")
    lines.append(f"  • 平均成本：{chip.avg_cost:.2f}元（当前价{chip.y[-1]:.2f}元，距成本{chip.y[-1] - chip.avg_cost:+.2f}元）")
    r90 = chip.percent_chips['90']
    r70 = chip.percent_chips['70']
    pct = r90['concentration'] * 100
    lines.append("  \u2022 90%筹码区间：{l}~{h}元（集中度{p:.1f}%）".format(
        l=r90['priceRange'][0], h=r90['priceRange'][1], p=pct))
    pct2 = r70['concentration'] * 100
    lines.append("  \u2022 70%筹码区间：{l}~{h}元（集中度{p:.1f}%）".format(
        l=r70['priceRange'][0], h=r70['priceRange'][1], p=pct2))
    # 找峰值
    sorted_idx = np.argsort(chip.x)[::-1]
    top_count = max(1, int(len(chip.x) * 0.05))
    top_prices = sorted(chip.y[i] for i in sorted_idx[:top_count])
    lines.append(f"  • 筹码峰值：{min(top_prices):.2f}～{max(top_prices):.2f}元（最密集成本区）")
    # 风险提示
    if chip.benefit_part > 0.90:
        lines.append(f"  ⚠️ 风险：{chip.benefit_part:.0%}筹码已获利，高位换手率放大，警惕集中兑现")
    elif chip.benefit_part < 0.30:
        lines.append(f"  ⚠️ 机会：仅{chip.benefit_part:.0%}筹码获利，多数筹码被套，下方支撑较强")
    else:
        lines.append(f"  ✅ 健康：筹码分布相对均衡，未出现极端获利/套牢压力")
    return "\n".join(lines)


def print_chip_report(chip: ChipData, stock_code: str = "") -> None:
    """打印筹码分布分析报告"""
    print(f"\n{'='*55}")
    print(f"  CYQ筹码分布报告 {f'({stock_code})' if stock_code else ''}")
    print(f"{'='*55}")
    print(f"  数据截止: {chip.date}  计算天数: {chip.trading_days}日")
    print(f"\n  ◆ 获利比例: {chip.benefit_part:.2%}  （当前价以下筹码占比）")
    print(f"  ◆ 平均成本: {chip.avg_cost:.2f}元  （50%分位成本）")
    print(f"\n  ◆ 90%筹码区间: {chip.percent_chips['90']['priceRange'][0]} ~ "
          f"{chip.percent_chips['90']['priceRange'][1]}元")
    print(f"    集中度: {chip.percent_chips['90']['concentration']:.2%}")
    print(f"  ◆ 70%筹码区间: {chip.percent_chips['70']['priceRange'][0]} ~ "
          f"{chip.percent_chips['70']['priceRange'][1]}元")
    print(f"    集中度: {chip.percent_chips['70']['concentration']:.2%}")

    # 找筹码峰值区间（top5%）
    sorted_idx = np.argsort(chip.x)[::-1]
    top_count = max(1, int(len(chip.x) * 0.05))
    top_indices = sorted_idx[:top_count]
    peak_prices = [chip.y[i] for i in top_indices]
    peak_range = f"{min(peak_prices):.2f} ~ {max(peak_prices):.2f}"
    print(f"\n  ◆ 筹码峰值区间: {peak_range}元  （最密集成本区）")

    # 成本分布可视化（简化ASCII）
    print(f"\n  筹码分布（价格从低到高，每10格取1点）:")
    step = max(1, len(chip.x) // 20)
    max_bar = 30
    max_val = max(chip.x[::step]) if len(chip.x) > 0 else 0
    bars = []
    for i in range(0, len(chip.x), step):
        bar_len = int(chip.x[i] / max_val * max_bar) if max_val > 0 else 0
        price = chip.y[i]
        bars.append((price, bar_len))
    for price, bar in bars:
        bar_str = "█" * bar + "░" * (max_bar - bar)
        print(f"    {price:>7.2f} │{bar_str}")
    print(f"{'='*55}")


# ============================================================
# 测试：以600351亚宝药业为例
# ============================================================
if __name__ == "__main__":
    import sqlite3, baostock as bs

    code = "600351"
    bs.login()
    rs = bs.query_history_k_data_plus(
        f"sh.{code}",
        "date,open,high,low,close,volume,amount,pctChg",
        start_date="2024-07-01", end_date="2026-04-30",
        frequency="d", adjustflag="2"
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    fields = rs.fields
    bs.logout()

    df = pd.DataFrame(rows, columns=fields)
    for col in ["open", "high", "low", "close", "volume", "amount", "pctChg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # 从东财获取换手率（需要单独接口），暂时用固定模拟值演示
    # 实际使用时可从东财或AKShare补充换手率字段
    # 这里用成交量/流通股本估算（简化版，仅演示）
    df["turnover"] = 1.5  # 模拟换手率1.5%，真实场景需接入换手率数据源

    print(f"Loaded {len(df)} bars, date range: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")

    # 计算210日筹码分布
    chip = calc_chip_distribution(
        df,
        accuracy_factor=150,
        trading_days=210,
        target_date=None  # 取最后一日
    )
    print_chip_report(chip, code)
