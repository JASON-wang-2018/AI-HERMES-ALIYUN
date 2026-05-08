#!/usr/bin/env python3
"""
A股主升浪四条铁律分析器
基于《一本书看透股市庄家》提炼的主升浪启动信号量化系统
"""
import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional


class RisingWaveAnalyzer:
    """主升浪四条铁律分析器"""

    def __init__(self):
        bs.login()

    def __del__(self):
        try:
            bs.logout()
        except:
            pass

    def analyze(self, code: str, name: str = '', surge_threshold: float = 5.0) -> dict:
        """
        分析单只股票的主升浪四条铁律

        Args:
            code: 股票代码，格式 sz.000600 或 000600
            name: 股票名称
            surge_threshold: 大阳线标准（主板默认5%，创业板/科创板10%）

        Returns:
            dict: 包含scores/results/details/total/rules_met/prob等字段
        """
        if not code.startswith('sz.') and not code.startswith('sh.'):
            code = 'sz.' + code if code.startswith('0') else 'sh.' + code

        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

        rs = bs.query_history_k_data_plus(code,
            'date,open,high,low,close,volume,turn,pctChg',
            start_date=start, end_date=end, frequency='d', adjustflag='2')
        data = []
        while rs.error_code == '0' and rs.next():
            data.append(rs.get_row_data())
        df = pd.DataFrame(data, columns=rs.fields)
        for col in ['open', 'high', 'low', 'close', 'pctChg', 'turn', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        df = df.dropna(subset=['close']).sort_values('date').reset_index(drop=True)

        if len(df) < 20:
            return {'error': f'数据不足({len(df)}天)，需要至少20天)'}

        today = df.iloc[-1]
        # 取近21日（排除今天，用于铁律1的20日统计）
        lookback = df.tail(22).copy()
        if len(lookback) > 21:
            lookback = lookback.iloc[:-1]

        scores = {}
        results = {}
        details = {}

        # ===== 铁律1：高质量大阳线（横盘缩量+量能放大）=====
        big_surge = lookback[lookback['pctChg'] >= surge_threshold].copy()
        rule1_score = 0
        rule1_status = f"20日内无>{surge_threshold}%大阳线"
        rule1_detail = {}

        if len(big_surge) > 0:
            best = big_surge.loc[big_surge['pctChg'].idxmax()]
            best_date = best['date']
            best_pct = best['pctChg']
            best_turn = best['turn']

            # 大阳启动日前最多15日横盘数据
            pre = lookback[lookback['date'] < best_date].tail(15)

            if len(pre) >= 5:
                lat_hi = pre['high'].max()
                lat_lo = pre['low'].min()
                lat_range = (lat_hi - lat_lo) / lat_lo * 100

                pre5_vol = pre.tail(5)['volume'].mean()
                pre15_vol = pre['volume'].mean()
                vol_shrink = pre5_vol / pre15_vol if pre15_vol > 0 else 1

                pre15_turn = pre['turn'].mean()
                turn_ratio = best_turn / pre15_turn if pre15_turn > 0 else 0

                rule1_detail = {
                    '大阳日': best_date.strftime('%m-%d'),
                    '涨幅': f"{best_pct:.2f}%",
                    '换手': f"{best_turn:.2f}%",
                    '横盘振幅': f"{lat_range:.1f}%",
                    '缩量比(前5/前15均量)': f"{vol_shrink:.2f}x",
                    '量能放大(大阳/前15均换手)': f"{turn_ratio:.2f}x"
                }

                lat_ok = lat_range < 15
                shr_ok = vol_shrink < 0.7
                vol_ok = turn_ratio >= 1.5

                if lat_ok and shr_ok and vol_ok:
                    rule1_score = 10
                    rule1_status = f"完全符合(振幅{lat_range:.1f}%缩量{vol_shrink:.2f}x量{turn_ratio:.1f}x)"
                elif lat_ok and vol_ok:
                    rule1_score = 7
                    rule1_status = "横盘好但未缩量"
                elif shr_ok and vol_ok:
                    rule1_score = 7
                    rule1_status = "缩量好但横盘不够窄"
                elif vol_ok:
                    rule1_score = 5
                    rule1_status = "仅量能达标"
                else:
                    rule1_score = 2
                    rule1_status = "不符合"

        scores['铁律1_高质量大阳'] = rule1_score
        results['铁律1_高质量大阳'] = rule1_status
        details['铁律1_高质量大阳'] = rule1_detail

        # ===== 铁律2：向上缺口三日不回补 =====
        rule2_score = 0
        rule2_status = "无向上缺口"
        rule2_detail = {}

        if len(big_surge) > 0:
            best = big_surge.loc[big_surge['pctChg'].idxmax()]
            idx_list = df[df['date'] == best['date']].index.tolist()
            if idx_list:
                idx = idx_list[0]
                if idx > 0:
                    prev_close = df.iloc[idx - 1]['close']
                    gap_low = best['low']

                    if gap_low > prev_close:
                        gap_size = (gap_low - prev_close) / prev_close * 100
                        post = df.iloc[idx + 1:idx + 4]
                        fill_day = None
                        for i, (_, row) in enumerate(post.iterrows()):
                            if row['low'] <= gap_low:
                                fill_day = i + 1
                                break

                        rule2_detail = {
                            '缺口日': best['date'].strftime('%m-%d'),
                            '缺口大小': f"{gap_size:.2f}%",
                            '缺口区间': f"{prev_close:.2f}~{gap_low:.2f}",
                            '3日内回补': f"{'否(保留'+str(len(post))+'日)' if fill_day is None else '第'+str(fill_day)+'日回补'}"
                        }

                        if fill_day is None:
                            rule2_score = 10
                            rule2_status = f"保留{len(post)}日未补"
                        else:
                            rule2_score = max(0, 10 - fill_day * 3)
                            rule2_status = f"第{fill_day}日回补"

        scores['铁律2_缺口不补'] = rule2_score
        results['铁律2_缺口不补'] = rule2_status
        details['铁律2_缺口不补'] = rule2_detail

        # ===== 铁律3：阶梯式连阳（每日收阳且收盘创新高）=====
        rule3_score = 0
        rule3_status = "无有效信号"
        rule3_detail = {}

        if len(df) >= 5:
            consec = 0
            max_past = float('-inf')
            sorted_df = df.sort_values('date')

            for i in range(len(sorted_df) - 1, -1, -1):
                row = sorted_df.iloc[i]
                if row['pctChg'] > 0 and row['close'] > max_past:
                    consec += 1
                    max_past = row['close']
                else:
                    break

            rule3_detail = {'连续收阳创新高': f"{consec}日"}

            if consec >= 4:
                rule3_score = 10
                rule3_status = f"连续{consec}日"
            elif consec == 3:
                rule3_score = 8
                rule3_status = f"连续{consec}日接近"
            elif consec == 2:
                rule3_score = 5
                rule3_status = f"仅{consec}日"
            else:
                rule3_score = 2
                rule3_status = f"仅{consec}日不成形"

        scores['铁律3_阶梯连阳'] = rule3_score
        results['铁律3_阶梯连阳'] = rule3_status
        details['铁律3_阶梯连阳'] = rule3_detail

        # ===== 铁律4：关键位放量突破 =====
        rule4_score = 0
        rule4_status = "无大阳线无法判断"
        rule4_detail = {}

        if len(big_surge) > 0:
            best = big_surge.loc[big_surge['pctChg'].idxmax()]
            idx_list = df[df['date'] == best['date']].index.tolist()
            if idx_list:
                idx = idx_list[0]
                pre20 = df.iloc[max(0, idx - 20):idx]
                if len(pre20) > 0:
                    key_level = pre20['high'].max()
                    close = best['close']
                    turn = best['turn']
                    pre20_turn = pre20['turn'].mean()
                    vol_ratio = turn / pre20_turn if pre20_turn > 0 else 0
                    broken = close > key_level

                    rule4_detail = {
                        '关键位(前20日高点)': f"{key_level:.2f}",
                        '突破日收盘': f"{close:.2f}",
                        '是否突破': '是' if broken else '否',
                        '量能放大': f"{vol_ratio:.2f}x"
                    }

                    if broken and vol_ratio >= 1.5:
                        rule4_score = 10
                        rule4_status = f"突破{key_level}放量{vol_ratio:.1f}倍"
                    elif broken:
                        rule4_score = 6
                        rule4_status = f"突破{key_level}但量能不足"
                    else:
                        rule4_score = 2
                        rule4_status = f"未突破{key_level}"

        scores['铁律4_关键位放量'] = rule4_score
        results['铁律4_关键位放量'] = rule4_status
        details['铁律4_关键位放量'] = rule4_detail

        # ===== 综合评分 =====
        total = sum(scores.values())
        rules_met = sum(1 for s in scores.values() if s >= 7)

        if rules_met >= 4:
            prob = 92
        elif rules_met == 3:
            prob = 86
        elif rules_met == 2:
            prob = 74
        elif rules_met == 1:
            prob = 48
        else:
            prob = 20

        return {
            'code': code.replace('sz.', '').replace('sh.', ''),
            'name': name,
            'date': today['date'].strftime('%Y-%m-%d'),
            'close': f"{today['close']:.2f}",
            'scores': scores,
            'results': results,
            'details': details,
            'total': total,
            'rules_met': rules_met,
            'prob': prob
        }

    def batch_analyze(self, stocks: list, names: list = None, thresholds: dict = None) -> list:
        """
        批量分析多只股票

        Args:
            stocks: 股票代码列表 ['000600', '002715']
            names: 股票名称列表 ['建投能源', '登云股份']
            thresholds: 大阳线阈值 {'000600': 5.0, '002715': 10.0}

        Returns:
            按prob概率降序排列的结果列表
        """
        if names is None:
            names = [''] * len(stocks)
        if thresholds is None:
            thresholds = {}
        if len(names) != len(stocks):
            names = [''] * len(stocks)

        results = []
        for code, name in zip(stocks, names):
            # 自动判断阈值：创业板(300/301开头)=10%，主板=5%
            c = code.replace('sz.', '').replace('sh.', '')
            if c.startswith('30') or c.startswith('688'):
                thresh = thresholds.get(code, 10.0)
            else:
                thresh = thresholds.get(code, 5.0)

            r = self.analyze(code, name, surge_threshold=thresh)
            results.append(r)

        # 按prob降序排列
        results.sort(key=lambda x: x.get('prob', 0), reverse=True)
        return results

    def print_report(self, result: dict):
        """格式化打印分析报告"""
        if 'error' in result:
            print(f"错误: {result['error']}")
            return

        print(f"\n{'='*60}")
        print(f"【{result['name']}({result['code']}) 主升浪四条铁律分析】")
        print(f"分析日期: {result['date']}  收盘: {result['close']}元")
        print()
        print("【四条铁律判定】")
        for k in result['scores']:
            s = result['scores'][k]
            icon = "✅" if s >= 7 else "⚠️" if s >= 4 else "❌"
            print(f"  {k}: {icon} {result['results'][k]} (得分{s}/10)")
        print()
        print(f"【综合结果】")
        print(f"  综合得分: {result['total']}/40  共振: {result['rules_met']}/4  主升浪成功概率: {result['prob']}%")
        print()
        print("【详细数据】")
        for k, v in result['details'].items():
            print(f"  {k}: {v}")


if __name__ == '__main__':
    import sys

    analyzer = RisingWaveAnalyzer()

    if len(sys.argv) == 1:
        # 默认分析000600
        r = analyzer.analyze('sz.000600', '建投能源', surge_threshold=5.0)
        analyzer.print_report(r)
    elif len(sys.argv) == 2:
        code = sys.argv[1]
        r = analyzer.analyze(code, code, surge_threshold=5.0)
        analyzer.print_report(r)
    elif len(sys.argv) == 3:
        code, thresh = sys.argv[1], float(sys.argv[2])
        r = analyzer.analyze(code, code, surge_threshold=thresh)
        analyzer.print_report(r)
    else:
        print("用法: python a_stock_rising_wave.py [代码] [大阳线阈值]")
        print("示例: python a_stock_rising_wave.py 000600 5.0")
