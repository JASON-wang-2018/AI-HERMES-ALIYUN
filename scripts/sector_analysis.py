#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题材强度 + 龙头识别程序 | 短线量化模型 第二层 + 第三层
功能：识别最强题材Top3 + 识别龙头股

使用方式：
    python3 scripts/sector_analysis.py
    python3 scripts/sector_analysis.py 20260427
"""

import akshare as ak
import pandas as pd
import sys
from datetime import datetime, timedelta


# ============================================================
# 工具函数
# ============================================================

def get_zt_data(date: str) -> dict:
    """获取涨跌停数据"""
    try:
        zt = ak.stock_zt_pool_em(date=date)
        dt = ak.stock_zt_pool_dtgc_em(date=date)
        zbgc = ak.stock_zt_pool_zbgc_em(date=date)
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        return {}

    return {
        'zt': zt,
        'dt': dt,
        'zbgc': zbgc,
        'zt_count': len(zt),
        'dt_count': len(dt),
        'zbgc_count': len(zbgc),
        'date': date,
    }


# ============================================================
# 第二层：题材强度评分
# ============================================================

def calc_sector_strength(zt: pd.DataFrame) -> pd.DataFrame:
    """
    计算题材强度
    公式：0.4×涨停数量 + 0.3×连板高度 + 0.2×封单强度 + 0.1×板块成交额

    归一化处理：各指标先max-min归一化，再加权求和
    """
    if len(zt) == 0:
        return pd.DataFrame()

    # 板块聚合
    sector = zt.groupby('所属行业').agg(
        涨停数=('代码', 'count'),
        成交额合计=('成交额', 'sum'),
        封单合计=('封板资金', 'sum'),
        最高连板=('连板数', 'max'),
        平均换手率=('换手率', 'mean'),
        总市值合计=('总市值', 'sum'),
    ).reset_index()

    # 归一化（0-100）
    def normalize(series):
        mn, mx = series.min(), series.max()
        if mx == mn:
            return series * 0 + 50
        return (series - mn) / (mx - mn) * 100

    sector['涨停数_n'] = normalize(sector['涨停数'])
    sector['最高连板_n'] = normalize(sector['最高连板'])
    sector['封单合计_n'] = normalize(sector['封单合计'])
    sector['成交额_n'] = normalize(sector['成交额合计'])

    # 加权求和
    sector['题材强度分'] = (
        0.4 * sector['涨停数_n'] +
        0.3 * sector['最高连板_n'] +
        0.2 * sector['封单合计_n'] +
        0.1 * sector['成交额_n']
    )

    # 也计算简单版（涨停数排名 × 连板加成）
    sector['简单强度'] = sector['涨停数'] * 10 + sector['最高连板'] * 5

    sector = sector.sort_values('题材强度分', ascending=False).reset_index(drop=True)
    return sector


def format_sector_report(sector_df: pd.DataFrame, top_n: int = 5) -> str:
    """格式化题材报告"""
    if len(sector_df) == 0:
        return "⚠️ 今日无涨停数据"

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"📈 题材强度排行榜 Top{top_n} | {sector_df.iloc[0]['题材强度分']:.1f}分以上")
    lines.append(f"{'='*55}")
    lines.append(f"{'排名':>4}  {'题材':^12} {'涨停':^5} {'最高连板':^6} {'题材强度':^8} {'简单强度':^8}")
    lines.append(f"{'-'*55}")

    for i, row in sector_df.head(top_n).iterrows():
        medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else f" {i+1} "))
        lines.append(
            f"{medal:>5} {row['所属行业']:^12} "
            f"{int(row['涨停数']):^5} {int(row['最高连板']):^6}板 "
            f"{row['题材强度分']:^8.1f} {row['简单强度']:^8.0f}"
        )

    # 分类
    top3 = sector_df.head(3)
    lines.append(f"\n{'='*55}")
    lines.append(f"🔥 主线题材（Top3）:")
    for i, row in top3.iterrows():
        lines.append(f"  {row['所属行业']} — 涨停{int(row['涨停数'])}家 最高{int(row['最高连板'])}板")

    if len(sector_df) > 3:
        lines.append(f"\n⏸️ 次主线（4~5名）:")
        for i, row in sector_df.iloc[3:5].iterrows():
            lines.append(f"  {row['所属行业']} — 涨停{int(row['涨停数'])}家")

    return "\n".join(lines)


# ============================================================
# 第三层：龙头识别
# ============================================================

def identify_dragons(zt: pd.DataFrame, top_sectors: list) -> pd.DataFrame:
    """
    识别龙头股

    龙头条件（满足3条以上）：
    1. 连板高度 = 板块第一
    2. 首板时间最早（时间优先）
    3. 封单金额最大
    4. 换手合理（非一字死板）：换手率 1%~20%
    """
    if len(zt) == 0:
        return pd.DataFrame()

    dragons = []

    for sector in top_sectors:
        sector_stocks = zt[zt['所属行业'] == sector].copy()
        if len(sector_stocks) == 0:
            continue

        # 计算各指标排名（越小越强）
        sector_stocks['连板排名'] = sector_stocks['连板数'].rank(ascending=False, method='min')
        sector_stocks['首板时间_数值'] = sector_stocks['首次封板时间'].astype(str).str.zfill(6).apply(
            lambda x: int(x) if x.isdigit() else 999999
        )
        sector_stocks['封单排名'] = sector_stocks['封板资金'].rank(ascending=False, method='min')

        # 换手率合理：1% < 换手率 < 25%
        sector_stocks['换手合理'] = sector_stocks['换手率'].between(0.5, 25).astype(int)

        # 计算龙头得分（满足条件数）
        sector_stocks['龙头得分'] = (
            (sector_stocks['连板排名'] == 1).astype(int) +      # 条件1
            (sector_stocks['首板时间_数值'] <= sector_stocks['首板时间_数值'].min() + 5).astype(int) +  # 条件2（最早5分钟内）
            (sector_stocks['封单排名'] == 1).astype(int) +        # 条件3
            sector_stocks['换手合理']                             # 条件4
        )

        # 分类
        sector_stocks['龙类型'] = sector_stocks['龙头得分'].apply(
            lambda x: '🐉 真龙' if x >= 3 else ('🐉 次龙' if x == 2 else '🐍 跟风')
        )

        dragons.append(sector_stocks)

    if not dragons:
        return pd.DataFrame()

    result = pd.concat(dragons, ignore_index=True)
    result = result.sort_values(['龙头得分', '连板数', '封板资金'],
                                ascending=[False, False, False])
    return result


def format_dragon_report(dragons: pd.DataFrame, top_sectors: list) -> str:
    """格式化龙头报告"""
    if len(dragons) == 0:
        return "⚠️ 无龙头数据"

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"🐉 龙头识别报告")
    lines.append(f"{'='*55}")

    for sector in top_sectors:
        sector_dragons = dragons[dragons['所属行业'] == sector]
        if len(sector_dragons) == 0:
            continue

        # 找出该板块真龙/次龙
        real_dragon = sector_dragons[sector_dragons['龙类型'] == '🐉 真龙']
        sub_dragon = sector_dragons[sector_dragons['龙类型'] == '🐉 次龙']

        lines.append(f"\n【{sector}】")
        lines.append(f"  涨停家数: {len(sector_dragons)}")

        if len(real_dragon) > 0:
            for _, row in real_dragon.iterrows():
                fengdan_str = f"{row['封板资金']/1e4:.0f}万"
                first_time = str(row['首次封板时间'])
                lines.append(
                    f"  🐉 真龙: {row['名称']}({row['代码']}) "
                    f"{int(row['连板数'])}板 | 封单:{fengdan_str} | "
                    f"首封:{first_time} | 换手:{row['换手率']:.1f}%"
                )

        if len(sub_dragon) > 0:
            for _, row in sub_dragon.head(2).iterrows():
                fengdan_str = f"{row['封板资金']/1e4:.0f}万"
                first_time = str(row['首次封板时间'])
                lines.append(
                    f"  🐉 次龙: {row['名称']}({row['代码']}) "
                    f"{int(row['连板数'])}板 | 封单:{fengdan_str} | "
                    f"首封:{first_time} | 换手:{row['换手率']:.1f}%"
                )

        # 跟风股（不操作）
        fenggeng = sector_dragons[sector_dragons['龙类型'] == '🐍 跟风']
        if len(fenggeng) > 0:
            names = "、".join(fenggeng['名称'].head(3).tolist())
            if len(fenggeng) > 3:
                names += "..."
            lines.append(f"  🐍 跟风（不参与）: {names}")

    # 全市场真龙汇总
    real_all = dragons[dragons['龙类型'] == '🐉 真龙']
    lines.append(f"\n{'='*55}")
    lines.append(f"📋 全市场真龙/次龙汇总")
    lines.append(f"{'='*55}")
    if len(real_all) > 0:
        for _, row in real_all.iterrows():
            fengdan_str = f"{row['封板资金']/1e8:.2f}亿" if row['封板资金'] > 1e8 else f"{row['封板资金']/1e4:.0f}万"
            lines.append(
                f"  🐉 {row['名称']}({row['代码']}) | "
                f"{int(row['连板数'])}板 | {row['所属行业']} | "
                f"封单{fengdan_str} | 换手{row['换手率']:.1f}%"
            )

    sub_all = dragons[dragons['龙类型'] == '🐉 次龙']
    if len(sub_all) > 0:
        for _, row in sub_all.head(5).iterrows():
            fengdan_str = f"{row['封板资金']/1e8:.2f}亿" if row['封板资金'] > 1e8 else f"{row['封板资金']/1e4:.0f}万"
            lines.append(
                f"  🐉 次龙 {row['名称']}({row['代码']}) | "
                f"{int(row['连板数'])}板 | {row['所属行业']} | "
                f"封单{fengdan_str}"
            )

    return "\n".join(lines)


# ============================================================
# 合并二三层的完整题材+龙头报告
# ============================================================

def build_top_sector_detail(zt: pd.DataFrame, sector_name: str, n: int = 3) -> pd.DataFrame:
    """对指定题材板块，取出其涨停股详情"""
    sector_stocks = zt[zt['所属行业'] == sector_name].copy()
    if len(sector_stocks) == 0:
        return pd.DataFrame()
    sector_stocks = sector_stocks.sort_values(['连板数', '封板资金'], ascending=[False, False])
    return sector_stocks.head(n)


def format_trade_recommendation(
    sector_df: pd.DataFrame,
    dragons: pd.DataFrame,
    top_sectors: list,
    emotion_phase: str
) -> str:
    """生成可操作的操作建议"""
    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"📋 短线操作建议")
    lines.append(f"{'='*55}")

    # 操作前提
    lines.append(f"\n情绪周期: {emotion_phase}")
    lines.append(f"可操作题材数: {len(top_sectors)}")

    if emotion_phase in ["🔴 冰点", "数据获取失败"]:
        lines.append(f"\n⚠️ 当前非操作窗口，建议观望")
        return "\n".join(lines)

    # 按题材给出建议
    for sector in top_sectors:
        sector_dragons = dragons[dragons['所属行业'] == sector]
        real = sector_dragons[sector_dragons['龙类型'] == '🐉 真龙']
        sub = sector_dragons[sector_dragons['龙类型'] == '🐉 次龙']

        if len(real) == 0 and len(sub) == 0:
            continue

        lines.append(f"\n【{sector}】")
        lines.append(f"  涨停{int(len(sector_dragons))}家")

        if len(real) > 0:
            r = real.iloc[0]
            # 打板条件判断
            fengdan_ratio = r['封板资金'] / r['流通市值'] * 100
            zhenggui = 0.5 < r['换手率'] < 25

            can_board = (
                r['连板数'] >= 2 and
                fengdan_ratio >= 1.0 and
                zhenggui
            )

            lines.append(f"\n  🐉 真龙: {r['名称']}({r['代码']}) {int(r['连板数'])}板")
            if can_board:
                lines.append(f"     → 打板信号: ✅满足（封单比{fengdan_ratio:.1f}%, 换手{r['换手率']:.1f}%）")
            else:
                reasons = []
                if r['连板数'] < 2: reasons.append("连板不足2")
                if fengdan_ratio < 1.0: reasons.append(f"封单比{fengdan_ratio:.1f}%<1%")
                if not zhenggui: reasons.append(f"换手{'过低' if r['换手率'] <= 0.5 else '过高'}")
                lines.append(f"     → 打板信号: ❌ {', '.join(reasons)}")

            if len(sub) > 0:
                s = sub.iloc[0]
                lines.append(f"  🐉 次龙: {s['名称']}({s['代码']}) {int(s['连板数'])}板")
                lines.append(f"     → 低吸参考: 回调{int(s['连板数'])}板后缩量站稳MA5")

    return "\n".join(lines)


# ============================================================
# 主程序
# ============================================================

def main():
    if len(sys.argv) >= 2:
        date = sys.argv[1]
    else:
        yesterday = datetime.now() - timedelta(days=1)
        date = yesterday.strftime("%Y%m%d")

    print(f"\n📡 正在拉取 {date} 数据...")

    data = get_zt_data(date)
    if not data:
        return

    zt = data['zt']
    zt_count = data['zt_count']

    if zt_count == 0:
        print("⚠️ 今日无涨停数据")
        return

    # ---- 第二层：题材强度 ----
    sector_df = calc_sector_strength(zt)
    top5_sectors = sector_df.head(5)['所属行业'].tolist()
    top3_sectors = sector_df.head(3)['所属行业'].tolist()

    print(format_sector_report(sector_df, top_n=5))

    # ---- 第三层：龙头识别 ----
    dragons = identify_dragons(zt, top5_sectors)
    print(format_dragon_report(dragons, top5_sectors))

    # ---- 操作建议 ----
    emotion_phase = "⚪ 震荡"  # 情绪周期由 emotion_analysis.py 产出，这里默认
    print(format_trade_recommendation(sector_df, dragons, top3_sectors, emotion_phase))

    # ---- 详细数据表（可保存）----
    print(f"\n{'='*55}")
    print(f"📊 Top3题材涨停股明细")
    print(f"{'='*55}")
    for sector in top3_sectors:
        detail = build_top_sector_detail(zt, sector, n=5)
        if len(detail) == 0:
            continue
        print(f"\n【{sector}】")
        cols = ['名称', '代码', '连板数', '涨跌幅', '换手率', '封板资金', '首次封板时间', '所属行业']
        available_cols = [c for c in cols if c in detail.columns]
        print(detail[available_cols].to_string(index=False))


if __name__ == "__main__":
    main()
