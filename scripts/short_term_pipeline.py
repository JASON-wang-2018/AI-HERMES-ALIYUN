#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短线量化完整流水线 | 三层合一
第一层：情绪周期识别（系统开关）
第二层：题材强度评分（Top3主线）
第三层：龙头识别（真龙/次龙 + 买入信号）

使用方式：
    python3 scripts/short_term_pipeline.py
    python3 scripts/short_term_pipeline.py 20260427
"""

import akshare as ak
import pandas as pd
import sys
from datetime import datetime, timedelta


# ============================================================
# 第一层：情绪周期识别
# ============================================================

def get_emotion_data(date: str) -> dict:
    """
    获取情绪数据（涨停池 + 市场整体换手率）

    换手率数据来自 akshare index_zh_a_hist_arc，
    通过沪深市场总成交量/总股本估算全市场换手率。
    参考 ZhuLinsen/daily_stock_analysis emotion_cycle 策略的量化体系：
      < 0.5%/日 → 冷淡底部（买入信号）
      0.5~2%   → 正常平稳
      2~5%     → 活跃（不宜追高）
      > 5%     → 高热度警惕
      > 10%    → 极度过热（短期顶部）
    """
    try:
        zt = ak.stock_zt_pool_em(date=date)
        dt = ak.stock_zt_pool_dtgc_em(date=date)
        zbgc = ak.stock_zt_pool_zbgc_em(date=date)
    except Exception as e:
        return {'error': str(e)}

    zt_count = len(zt)
    dt_count = len(dt)
    zbgc_count = len(zbgc) if zbgc is not None and len(zbgc) > 0 else 0

    # 炸板率
    if zt_count > 0 and zbgc_count > 0:
        zbgc_rate = zbgc_count / (zt_count + zbgc_count) * 100
    else:
        zbgc_rate = 0.0

    # 涨跌停比
    ztd_ratio = zt_count / max(dt_count, 1)

    # 连板情况
    lianban = zt[zt['连板数'] >= 2] if zt_count > 0 else pd.DataFrame()
    max_lianban = lianban['连板数'].max() if len(lianban) > 0 else 0
    lianban_count = len(lianban)

    # ── 全市场换手率估算 ────────────────────────────────
    # 用沪深A股日均成交额/总流通市值估算换手率
    market_turnover = None
    try:
        # 获取沪深主要指数成交量/成交额
        mkt = ak.stock_zh_index_spot_em(symbol="沪深京A股")
        if mkt is not None and len(mkt) > 0:
            total_vol = mkt['成交量'].sum() if '成交量' in mkt.columns else 0
            total_amt = mkt['成交额'].sum() if '成交额' in mkt.columns else 0
            # 沪深A股总流通市值估算（万元→亿元，假设平均股价8元）
            est_circulation = total_vol * 8 / 10000  # 亿股 * 8元 = 亿元
            if est_circulation > 0:
                market_turnover = round(total_amt / est_circulation / 1e8 * 100, 3)
    except Exception:
        pass

    # ── 近5日均量/近20日均量对比 ─────────────────────
    vol_ratio_5d_20d = None
    try:
        # 取沪深300日K
        hs300 = ak.stock_zh_index_daily(symbol="sh000300")
        if hs300 is not None and len(hs300) >= 25:
            vol_5d_avg = hs300['volume'].tail(5).mean()
            vol_20d_avg = hs300['volume'].tail(20).mean()
            if vol_20d_avg > 0:
                vol_ratio_5d_20d = round(vol_5d_avg / vol_20d_avg, 3)
    except Exception:
        pass

    return {
        'zt_count': zt_count,
        'dt_count': dt_count,
        'zbgc_count': zbgc_count,
        'zbgc_rate': zbgc_rate,
        'ztd_ratio': ztd_ratio,
        'max_lianban': max_lianban,
        'lianban_count': lianban_count,
        'zt': zt,
        'dt': dt,
        'zbgc': zbgc,
        'date': date,
        # ── 新增：换手率情绪数据 ──────────────────────
        'market_turnover': market_turnover,       # 全市场估算换手率%
        'vol_ratio_5d_20d': vol_ratio_5d_20d,   # 近5日均量/近20日均量
    }


def _score_turnover(em: dict, base_score: int, signals: list) -> tuple:
    """
    基于换手率的情绪评分（参考emotion_cycle策略）
    返回 (adjusted_score, turnover_signals)
    """
    score = base_score
    tsigs = []
    mto = em.get('market_turnover')
    vr = em.get('vol_ratio_5d_20d')

    if mto is None:
        return score, tsigs

    # 换手率区间评分
    if mto < 0.5:
        score += 14
        tsigs.append(f"换手率{mto:.2f}%：冷淡底部区域 ✅")
    elif mto < 1.0:
        score += 7
        tsigs.append(f"换手率{mto:.2f}%：偏低，谨慎乐观 ➕")
    elif mto < 2.0:
        tsigs.append(f"换手率{mto:.2f}%：正常平稳区间 ➖")
    elif mto < 5.0:
        score -= 5
        tsigs.append(f"换手率{mto:.2f}%：市场活跃，不宜追高 ⚠️")
    elif mto < 10.0:
        score -= 12
        tsigs.append(f"换手率{mto:.2f}%：高热度区域，警惕 ⚠️")
    else:
        score -= 20
        tsigs.append(f"换手率{mto:.2f}%：极度过热，短期顶部风险 🔴")

    # 近5日量能对比（缩量=底部，放量=顶部）
    if vr is not None:
        if vr < 0.5:
            score += 8
            tsigs.append(f"量能缩至近20日{vr:.0%}，极度缩量 ✅（底部特征）")
        elif vr < 0.7:
            score += 4
            tsigs.append(f"量能缩至近20日{vr:.0%}，缩量整理 ➕")
        elif vr > 1.5:
            score -= 8
            tsigs.append(f"量能放大至近20日{vr:.0%}，脉冲放量 ⚠️（顶部特征）")
        elif vr > 2.0:
            score -= 14
            tsigs.append(f"量能放大至近20日{vr:.0%}，异常放大 🔴（主力出货嫌疑）")

    return score, tsigs


def identify_emotion_phase(em: dict) -> tuple:
    """
    识别情绪周期阶段（整合涨跌停比 + 炸板率 + 连板 + 换手率四维）

    Returns: (phase_icon, phase_name, score, signals, warning, action)
    """
    if 'error' in em:
        return ("❌", "数据获取失败", 0, [], True, "数据异常")

    zt = em['zt_count']
    dt = em['dt_count']
    ratio = em['ztd_ratio']
    zbgc_rate = em['zbgc_rate']
    max_lb = em['max_lianban']
    lb_cnt = em['lianban_count']

    score = 50
    signals = []

    # ── 涨跌停比打分 ─────────────────────────────────
    if ratio >= 3.0:
        score += 25
        signals.append(f"涨停/跌停比={ratio:.1f} ✅")
    elif ratio >= 1.5:
        score += 15
        signals.append(f"涨停/跌停比={ratio:.1f} ✅")
    elif ratio >= 1.0:
        score += 5
        signals.append(f"涨停/跌停比={ratio:.1f} ➕")
    elif ratio >= 0.5:
        score -= 10
        signals.append(f"涨停/跌停比={ratio:.1f} ⚠️")
    else:
        score -= 25
        signals.append(f"涨停/跌停比={ratio:.1f} 🔴")

    # ── 炸板率打分 ───────────────────────────────────
    if zbgc_rate <= 15:
        score += 15
        signals.append(f"炸板率={zbgc_rate:.1f}% ✅")
    elif zbgc_rate <= 25:
        score += 5
        signals.append(f"炸板率={zbgc_rate:.1f}% ➕")
    elif zbgc_rate <= 40:
        score -= 10
        signals.append(f"炸板率={zbgc_rate:.1f}% ⚠️")
    else:
        score -= 20
        signals.append(f"炸板率={zbgc_rate:.1f}% 🔴")

    # ── 连板情况 ──────────────────────────────────────
    if max_lb >= 5:
        score += 15
        signals.append(f"最高{max_lb}板 ✅")
    elif max_lb >= 3:
        score += 10
        signals.append(f"最高{max_lb}板 ➕")
    elif max_lb >= 2:
        score += 5
        signals.append(f"最高{max_lb}板 ➕")
    else:
        signals.append(f"最高{max_lb}板（连板高度低）")

    # ── 换手率情绪评分（新增维度四） ──────────────────
    score, turnover_signals = _score_turnover(em, score, signals)
    signals.extend(turnover_signals)

    # ── 冰点/主升判断 ────────────────────────────────
    if score >= 80:
        phase = ("🟢", "主升", "积极做多")
        warning = False
    elif score >= 65:
        phase = ("🔵", "修复", "轻仓试错")
        warning = False
    elif score >= 45:
        phase = ("⚪", "震荡", "观望/半仓")
        warning = False
    elif score >= 28:
        phase = ("🟡", "退潮", "防守为主")
        warning = True
    else:
        phase = ("🔴", "冰点", "空仓休息")
        warning = True

    return (phase[0], phase[1], score, signals, warning, phase[2])


def format_emotion_report(em: dict) -> str:
    """格式化情绪周期报告（整合四维评分）"""
    phase_icon, phase_name, score, signals, warning, action = identify_emotion_phase(em)

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"🌡️  第一层 | 情绪周期识别（系统开关）")
    lines.append(f"{'='*55}")
    lines.append(f"  日期：{em['date']}   得分：{score}/100")
    lines.append(f"  阶段：{phase_icon} {phase_name}  → {action}")
    lines.append(f"  涨停：{em['zt_count']}家   跌停：{em['dt_count']}家   炸板：{em['zbgc_count']}家")
    lines.append(f"  涨停/跌停比：{em['ztd_ratio']:.2f}   炸板率：{em['zbgc_rate']:.1f}%")
    lines.append(f"  连板股：{em['lianban_count']}家   最高：{em['max_lianban']}板")

    # 换手率数据展示（新增）
    mto = em.get('market_turnover')
    vr = em.get('vol_ratio_5d_20d')
    if mto is not None:
        lines.append(f"  全市场换手率：{mto:.3f}%")
    if vr is not None:
        lines.append(f"  近5日/20日量比：{vr:.3f}")

    if 'zt' in em and len(em['zt']) > 0:
        lb = em['zt'][em['zt']['连板数'] >= 2].sort_values('连板数', ascending=False)
        if len(lb) > 0:
            names = "、".join([f"{r['名称']}({int(r['连板数'])}板)" for _, r in lb.head(5).iterrows()])
            lines.append(f"  核心连板：{names}")

    lines.append(f"\n  信号明细：")
    for s in signals:
        lines.append(f"    {s}")

    if warning:
        lines.append(f"\n  ⚠️ 系统开关：OFF — 暂停进攻操作")

    return "\n".join(lines)


# ============================================================
# 第二层：题材强度评分
# ============================================================

def calc_sector_strength(zt: pd.DataFrame) -> pd.DataFrame:
    """计算题材强度"""
    if len(zt) == 0:
        return pd.DataFrame()

    sector = zt.groupby('所属行业').agg(
        涨停数=('代码', 'count'),
        成交额合计=('成交额', 'sum'),
        封单合计=('封板资金', 'sum'),
        最高连板=('连板数', 'max'),
        平均换手率=('换手率', 'mean'),
    ).reset_index()

    def normalize(series):
        mn, mx = series.min(), series.max()
        if mx == mn:
            return series * 0 + 50
        return (series - mn) / (mx - mn) * 100

    sector['涨停_n'] = normalize(sector['涨停数'])
    sector['连板_n'] = normalize(sector['最高连板'])
    sector['封单_n'] = normalize(sector['封单合计'])
    sector['成交_n'] = normalize(sector['成交额合计'])

    sector['题材强度分'] = (
        0.4 * sector['涨停_n'] +
        0.3 * sector['连板_n'] +
        0.2 * sector['封单_n'] +
        0.1 * sector['成交_n']
    )

    sector = sector.sort_values('题材强度分', ascending=False).reset_index(drop=True)
    return sector


def format_sector_report(sector_df: pd.DataFrame, top_n: int = 3) -> str:
    """格式化题材报告"""
    if len(sector_df) == 0:
        return ""

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"📈  第二层 | 题材强度排行榜 Top{top_n}")
    lines.append(f"{'='*55}")
    lines.append(f"  {'排名':^4}  {'题材':^12} {'涨停':^5} {'最高板':^6} {'强度分':^8}")
    lines.append(f"  {'-'*45}")

    medals = ["🥇", "🥈", "🥉", "  4", "  5"]
    for i, row in sector_df.head(top_n).iterrows():
        lines.append(
            f"  {medals[i]:^4} {row['所属行业']:^12} "
            f"{int(row['涨停数']):^5} {int(row['最高连板']):^5}板 "
            f"{row['题材强度分']:^8.1f}"
        )

    lines.append(f"\n  🔥 主线：{' / '.join(sector_df.head(3)['所属行业'].tolist())}")

    return "\n".join(lines)


# ============================================================
# 第三层：龙头识别 + 买入信号
# ============================================================

def identify_dragons(zt: pd.DataFrame, top_sectors: list) -> pd.DataFrame:
    """识别龙头股"""
    if len(zt) == 0:
        return pd.DataFrame()

    dragons = []
    for sector in top_sectors:
        sector_stocks = zt[zt['所属行业'] == sector].copy()
        if len(sector_stocks) == 0:
            continue

        sector_stocks['连板排名'] = sector_stocks['连板数'].rank(ascending=False, method='min')
        sector_stocks['首板时间_数值'] = (
            sector_stocks['首次封板时间'].astype(str).str.zfill(6)
            .apply(lambda x: int(x) if x.isdigit() else 999999)
        )
        sector_stocks['封单排名'] = sector_stocks['封板资金'].rank(ascending=False, method='min')

        # 换手合理区间
        sector_stocks['换手合理'] = sector_stocks['换手率'].between(0.5, 25).astype(int)

        # 封单/流通市值（封单强度）
        sector_stocks['封单强度'] = sector_stocks['封板资金'] / sector_stocks['流通市值'] * 100

        # 龙头得分
        sector_stocks['龙头得分'] = (
            (sector_stocks['连板排名'] == 1).astype(int) +
            (sector_stocks['首板时间_数值'] <= sector_stocks['首板时间_数值'].min() + 5).astype(int) +
            (sector_stocks['封单排名'] == 1).astype(int) +
            sector_stocks['换手合理']
        )

        sector_stocks['龙类型'] = sector_stocks['龙头得分'].apply(
            lambda x: '🐉 真龙' if x >= 3 else ('🐉 次龙' if x >= 2 else '🐍 跟风')
        )

        dragons.append(sector_stocks)

    if not dragons:
        return pd.DataFrame()

    result = pd.concat(dragons, ignore_index=True)
    result = result.sort_values(
        ['龙头得分', '连板数', '封板资金'], ascending=[False, False, False]
    )
    return result


def check_buy_signals(row: pd.Series) -> dict:
    """
    判断三种买入信号

    买入模型1【打板】：连板≥2 + 封单强度≥1% + 换手合理(0.5~25%)
    买入模型2【回封】：炸板后回封 + 回封时间<14:30 + 封单≥1亿
    买入模型3【低吸】：回调至MA5附近 + 缩量 + 当日分时均价上方
    """
    signals = []

    # 模型1：打板
    board_ok = (
        row['连板数'] >= 2 and
        row['封单强度'] >= 1.0 and
        0.5 < row['换手率'] < 25
    )
    signals.append(('📌 打板', board_ok,
        f"连板{int(row['连板数'])}≥2 ✅ | 封单强度{row['封单强度']:.2f}%≥1% ✅ | "
        f"换手{row['换手率']:.1f}%正常 ✅"
        if board_ok else
        f"连板{int(row['连板数'])} {'❌' if row['连板数'] < 2 else ''} | "
        f"封单强度{row['封单强度']:.2f}% {'❌' if row['封单强度'] < 1.0 else ''} | "
        f"换手{row['换手率']:.1f}% {'❌' if not (0.5 < row['换手率'] < 25) else ''}"
    ))

    # 模型3：低吸（回调到MA5，缩量）
    # 暂无MA数据，用换手率间接判断（实际需接入分时/均线数据）
    # 这里给出条件提示
    low_inj_signal = (
        row['连板数'] >= 1 and
        0.5 < row['换手率'] < 15 and
        row['龙类型'] in ['🐉 真龙', '🐉 次龙']
    )
    signals.append(('📥 低吸', low_inj_signal,
        f"缩量换手{row['换手率']:.1f}%(<15%) ✅ | 龙头{row['龙类型']} ✅"
        if low_inj_signal else
        f"换手{row['换手率']:.1f}% {'❌' if row['换手率'] >= 15 else ''} | "
        f"类型{row['龙类型']} {'❌' if row['龙类型'] == '🐍 跟风' else ''}"
    ))

    return {
        'signals': signals,
        'can_board': signals[0][1],   # 打板
        'can_low_inj': signals[1][1],  # 低吸
    }


def format_dragon_report(dragons: pd.DataFrame, top_sectors: list, emotion_phase: str) -> str:
    """格式化龙头报告"""
    if len(dragons) == 0:
        return ""

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"🐉  第三层 | 龙头识别 + 买入信号")
    lines.append(f"{'='*55}")

    for sector in top_sectors:
        sector_dr = dragons[dragons['所属行业'] == sector]
        if len(sector_dr) == 0:
            continue

        real = sector_dr[sector_dr['龙类型'] == '🐉 真龙']
        sub = sector_dr[sector_dr['龙类型'] == '🐉 次龙']
        fenggeng = sector_dr[sector_dr['龙类型'] == '🐍 跟风']

        lines.append(f"\n【{sector}】涨停{int(len(sector_dr))}家")

        for _, row in real.iterrows():
            fd = f"{row['封板资金']/1e8:.2f}亿" if row['封板资金'] > 1e8 else f"{row['封板资金']/1e4:.0f}万"
            signals = check_buy_signals(row)

            lines.append(f"\n  🐉 真龙：{row['名称']}({row['代码']}) {int(row['连板数'])}板")
            lines.append(f"     封单：{fd}  换手：{row['换手率']:.1f}%  首封：{row['首次封板时间']}")

            # 打板信号
            board_signal = signals['signals'][0]
            status = "✅" if board_signal[1] else "❌"
            lines.append(f"     📌 打板：{status} {board_signal[2]}")

            # 低吸信号
            inj_signal = signals['signals'][1]
            status2 = "✅" if inj_signal[1] else "❌"
            lines.append(f"     📥 低吸：{status2} {inj_signal[2]}")
            if inj_signal[1]:
                lines.append(f"        → 参考介入：回调{int(row['连板数'])}板后缩量站稳MA5介入")

        for _, row in sub.iterrows():
            fd = f"{row['封板资金']/1e8:.2f}亿" if row['封板资金'] > 1e8 else f"{row['封板资金']/1e4:.0f}万"
            signals = check_buy_signals(row)

            lines.append(f"\n  🐉 次龙：{row['名称']}({row['代码']}) {int(row['连板数'])}板")
            lines.append(f"     封单：{fd}  换手：{row['换手率']:.1f}%  首封：{row['首次封板时间']}")

            inj_signal = signals['signals'][1]
            status = "✅" if inj_signal[1] else "❌"
            lines.append(f"     📥 低吸：{status} {inj_signal[2]}")
            if inj_signal[1]:
                lines.append(f"        → 参考介入：回调{int(row['连板数'])}板后缩量站稳MA5介入")

        if len(fenggeng) > 0:
            names = "、".join([f"{r['名称']}({r['代码']})" for _, r in fenggeng.head(3).iterrows()])
            if len(fenggeng) > 3:
                names += "..."
            lines.append(f"\n  🐍 跟风（不参与）：{names}")

    return "\n".join(lines)


# ============================================================
# 综合操作建议
# ============================================================

def format_final_recommendation(
    em: dict,
    sector_df: pd.DataFrame,
    dragons: pd.DataFrame,
    top_sectors: list,
    phase_icon: str,
    phase_name: str,
    score: int,
    warning: bool
) -> str:
    """最终操作建议"""
    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"📋  综合操作建议")
    lines.append(f"{'='*55}")

    # 仓位建议
    if phase_name == "主升":
        position = "60~80%"
        action = "积极做多，精选真龙打板"
    elif phase_name == "修复":
        position = "30~50%"
        action = "轻仓试错，聚焦真龙/次龙"
    elif phase_name == "震荡":
        position = "20~30%"
        action = "半仓观望，快进快出"
    elif phase_name == "退潮":
        position = "0~10%"
        action = "防守为主，不追高位"
    else:  # 冰点
        position = "0%"
        action = "空仓休息，耐心等待"

    lines.append(f"\n  系统开关：{phase_icon} {phase_name}（{score}分）")
    lines.append(f"  仓位建议：{position}  → {action}")

    # 具体标的
    if not warning and len(dragons) > 0:
        real_all = dragons[dragons['龙类型'] == '🐉 真龙']
        sub_all = dragons[dragons['龙类型'] == '🐉 次龙']

        if len(real_all) > 0:
            boardables = []
            for _, r in real_all.iterrows():
                sigs = check_buy_signals(r)
                if sigs['can_board']:
                    boardables.append(f"{r['名称']}({r['代码']})")
            if boardables:
                lines.append(f"\n  📌 可打板标的：{' / '.join(boardables)}")

        if len(sub_all) > 0 or len(real_all) > 0:
            low_inj = []
            for _, r in pd.concat([real_all, sub_all]).iterrows():
                sigs = check_buy_signals(r)
                if sigs['can_low_inj']:
                    low_inj.append(f"{r['名称']}({r['代码']})")
            if low_inj:
                lines.append(f"\n  📥 可低吸标的：{' / '.join(low_inj[:5])}")

    # 止损纪律
    lines.append(f"\n  🛡️ 止损纪律（机械化，必须遵守）：")
    lines.append(f"     ① 打板：买入后炸板收盘 -5% 无条件止损")
    lines.append(f"     ② 低吸：买入后下跌 -3% 预警，-5% 必须出局")
    lines.append(f"     ③ 持仓超过 3 个交易日仍未启动，强制离场")
    lines.append(f"     ④ 板块当日冲高回落，隔日不反包，止损")

    # 今日禁区
    lines.append(f"\n  🚫 今日禁区：")
    lines.append(f"     ① 跟风股（龙类型=🐍）一律不追")
    lines.append(f"     ② 换手率>25%的高位股不接力")
    lines.append(f"     ③ 冰点/退潮期不抄底，不打板")

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

    print(f"\n{'#'*55}")
    print(f"#  短线量化完整流水线 | {date}")
    print(f"#{'#'*55}")

    # ---- 第一层 ----
    em = get_emotion_data(date)
    phase_icon, phase_name, score, signals, warning, action = identify_emotion_phase(em)
    print(format_emotion_report(em))

    # ---- 第二层 ----
    zt = em.get('zt', pd.DataFrame())
    if len(zt) > 0:
        sector_df = calc_sector_strength(zt)
        top3_sectors = sector_df.head(3)['所属行业'].tolist()
        top5_sectors = sector_df.head(5)['所属行业'].tolist()
        print(format_sector_report(sector_df, top_n=3))
    else:
        sector_df = pd.DataFrame()
        top3_sectors = []
        top5_sectors = []

    # ---- 第三层 ----
    if len(top5_sectors) > 0 and len(zt) > 0:
        dragons = identify_dragons(zt, top5_sectors)
        print(format_dragon_report(dragons, top5_sectors, phase_name))
    else:
        dragons = pd.DataFrame()

    # ---- 综合建议 ----
    if len(zt) > 0:
        print(format_final_recommendation(
            em, sector_df, dragons, top3_sectors,
            phase_icon, phase_name, score, warning
        ))

    print(f"\n{'#'*55}")
    print(f"#  流水线结束 | {date}")
    print(f"{'#'*55}\n")


if __name__ == "__main__":
    main()
