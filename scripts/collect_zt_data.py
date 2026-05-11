#!/usr/bin/env python3
"""
每日涨停数据采集入库脚本
- 数据源：AKShare (东方财富)
- 入库：SQLite (~/stock_knowledge/database/stock_data.db)
- 输出：reports/zt_{date}.json

使用方式：
    python3 scripts/collect_zt_data.py          # 今天
    python3 scripts/collect_zt_data.py 20260508  # 指定日期
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import json
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

VENV_PYTHON = '/home/admin/stock_knowledge/venv/bin/python3'
DB_PATH = '/home/admin/stock_knowledge/database/stock_data.db'
REPORTS_DIR = '/home/admin/stock_knowledge/reports'

def _safe_delay(seconds=3):
    time.sleep(random.uniform(seconds * 0.8, seconds * 1.5))

def get_zt_data(date_str):
    """获取指定日期涨跌停数据"""
    try:
        zt = ak.stock_zt_pool_em(date=date_str)
        dt = ak.stock_zt_pool_dtgc_em(date=date_str)
        zbgc = ak.stock_zt_pool_zbgc_em(date=date_str)
        return {
            'zt': zt,
            'dt': dt,
            'zbgc': zbgc,
            'zt_count': len(zt),
            'dt_count': len(dt),
            'zbgc_count': len(zbgc),
        }
    except Exception as e:
        print(f"  ❌ 数据获取失败: {e}")
        return None

def calc_sector_strength(zt_df):
    """计算板块强度"""
    if len(zt_df) == 0:
        return pd.DataFrame()
    sector = zt_df.groupby('所属行业').agg(
        涨停数=('代码', 'count'),
        成交额合计=('成交额', 'sum'),
        封单合计=('封板资金', 'sum'),
        最高连板=('连板数', 'max'),
        平均换手率=('换手率', 'mean'),
        总市值合计=('总市值', 'sum'),
    ).reset_index()
    sector = sector.sort_values('涨停数', ascending=False)
    return sector

def save_to_db(date_str, zt_df, dt_df, zbgc_df, sector_df):
    """保存到SQLite"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 写入每日市场汇总
    top3 = sector_df.head(3) if len(sector_df) >= 3 else sector_df
    summary = {
        'trade_date': date_str,
        'zt_count': len(zt_df),
        'dt_count': len(dt_df),
        'zbgc_count': len(zbgc_df),
        'top_sector': top3.iloc[0]['所属行业'] if len(top3) >= 1 else '',
        'top_sector_zt_count': int(top3.iloc[0]['涨停数']) if len(top3) >= 1 else 0,
        'second_sector': top3.iloc[1]['所属行业'] if len(top3) >= 2 else '',
        'second_sector_zt_count': int(top3.iloc[1]['涨停数']) if len(top3) >= 2 else 0,
        'third_sector': top3.iloc[2]['所属行业'] if len(top3) >= 3 else '',
        'third_sector_zt_count': int(top3.iloc[2]['涨停数']) if len(top3) >= 3 else 0,
        'top_sector_strength': float(top3.iloc[0]['涨停数'] * 10 + top3.iloc[0]['最高连板'] * 5) if len(top3) >= 1 else 0,
    }
    cursor.execute("""
        INSERT OR REPLACE INTO daily_market_summary
        (trade_date, zt_count, dt_count, zbgc_count,
         top_sector, top_sector_zt_count, second_sector, second_sector_zt_count,
         third_sector, third_sector_zt_count, top_sector_strength)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        summary['trade_date'], summary['zt_count'], summary['dt_count'], summary['zbgc_count'],
        summary['top_sector'], summary['top_sector_zt_count'],
        summary['second_sector'], summary['second_sector_zt_count'],
        summary['third_sector'], summary['third_sector_zt_count'],
        summary['top_sector_strength']
    ))

    # 写入涨停个股
    for _, row in zt_df.iterrows():
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO daily_zt_stocks
                (trade_date, seq, code, name, pct_chg, close, amount,
                 float_mkt_cap, total_mkt_cap, turnover_rate, seal_fund,
                 first_seal_time, last_seal_time, zbg_count, zt_stat, continuous_boards, sector)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date_str,
                int(row['序号']) if pd.notna(row['序号']) else None,
                str(row['代码']),
                str(row['名称']),
                float(row['涨跌幅']) if pd.notna(row['涨跌幅']) else None,
                float(row['最新价']) if pd.notna(row['最新价']) else None,
                float(row['成交额']) if pd.notna(row['成交额']) else None,
                float(row['流通市值']) if pd.notna(row['流通市值']) else None,
                float(row['总市值']) if pd.notna(row['总市值']) else None,
                float(row['换手率']) if pd.notna(row['换手率']) else None,
                float(row['封板资金']) if pd.notna(row['封板资金']) else None,
                str(row['首次封板时间']) if pd.notna(row['首次封板时间']) else '',
                str(row['最后封板时间']) if pd.notna(row['最后封板时间']) else '',
                int(row['炸板次数']) if pd.notna(row['炸板次数']) else 0,
                str(row['涨停统计']) if pd.notna(row['涨停统计']) else '',
                int(row['连板数']) if pd.notna(row['连板数']) else None,
                str(row['所属行业']) if pd.notna(row['所属行业']) else '',
            ))
        except Exception as e:
            print(f"  ⚠️ 写入 {row.get('代码','?')} 失败: {e}")

    conn.commit()
    conn.close()
    print(f"  ✅ 入库完成：涨停{len(zt_df)}只 跌停{len(dt_df)}只 炸板{len(zbgc_df)}只")

def save_json(date_str, zt_df, sector_df):
    """保存JSON到reports目录"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    out = {
        'date': date_str,
        'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'zt_count': len(zt_df),
        'top_sectors': sector_df.head(10).to_dict('records'),
        'zt_stocks': zt_df.to_dict('records'),
    }
    path = os.path.join(REPORTS_DIR, f'zt_{date_str}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON保存: {path}")

def main(date_str=None):
    if date_str is None:
        # 自动取前一交易日（如果是交易日早上9点前，今天就是查询日）
        today = datetime.now()
        if today.hour < 16:
            # 早上/盘中：查上一个交易日
            date_str = (today - timedelta(days=1)).strftime('%Y%m%d')
        else:
            date_str = today.strftime('%Y%m%d')

    # 格式化显示（统一用 YYYY-MM-DD 格式入库）
    display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    db_date = display_date  # 入库用同一格式

    print(f"\n{'='*50}")
    print(f"📊 涨停数据采集: {display_date}")
    print(f"{'='*50}")

    # Step1: 采集数据
    print(f"\n[1] 通过AKShare采集涨跌停数据...")
    _safe_delay(1)
    result = get_zt_data(date_str)
    if not result or result.get('zt') is None:
        print("  ❌ 采集失败，退出")
        return

    zt = result['zt']
    dt = result['dt']
    zbgc = result['zbgc']
    print(f"  涨停: {result['zt_count']}只  跌停: {result['dt_count']}只  炸板: {result['zbgc_count']}只")

    if len(zt) == 0:
        print("  ⚠️ 今日无涨停数据")
        return

    # Step2: 板块强度
    print(f"\n[2] 计算板块强度...")
    sector_df = calc_sector_strength(zt)
    print(f"  Top5强势板块:")
    for _, row in sector_df.head(5).iterrows():
        print(f"    {row['所属行业']}: 涨停{int(row['涨停数'])}只 最高{int(row['最高连板'])}板 成交{int(row['成交额合计']/1e8):.0f}亿")

    # Step3: 入库SQLite
    print(f"\n[3] 入库SQLite...")
    save_to_db(db_date, zt, dt, zbgc, sector_df)

    # Step4: 保存JSON
    print(f"\n[4] 保存JSON报告...")
    save_json(db_date, zt, sector_df)

    # Step5: 打印汇总
    print(f"\n{'='*50}")
    print(f"📋 {display_date} 涨停复盘汇总")
    print(f"{'='*50}")
    print(f"  涨停总数: {len(zt)}")
    print(f"  跌停总数: {len(dt)}")
    print(f"  炸板总数: {len(zbgc)}")
    print(f"  最强板块: {sector_df.iloc[0]['所属行业']} ({int(sector_df.iloc[0]['涨停数'])}只涨停)")
    if len(sector_df) >= 2:
        print(f"  第二板块: {sector_df.iloc[1]['所属行业']} ({int(sector_df.iloc[1]['涨停数'])}只涨停)")
    if len(sector_df) >= 3:
        print(f"  第三板块: {sector_df.iloc[2]['所属行业']} ({int(sector_df.iloc[2]['涨停数'])}只涨停)")
    print(f"\n  涨停股TOP5（按封单资金）:")
    top5 = zt.nlargest(5, '封板资金')
    for _, row in top5.iterrows():
        print(f"    {row['代码']} {row['名称']:<8} 封单:{row['封板资金']/1e8:>8.2f}亿 换手:{row['换手率']:.1f}% 行业:{row['所属行业']}")

if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(date_arg)
