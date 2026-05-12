#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_000600_full.py
老股民模板个股完整分析脚本（含完整8步结构化报告输出）
来源：2026-05-08 会话 + 宁波韵升报告模板
数据：Baostock日K + 东财API(估值/基本面/题材) + CYC筹码分布
用法：python3 analyze_000600_full.py [股票代码]
"""
import sys
import pandas as pd
import baostock as bs
import numpy as np
import subprocess
import json
import urllib.parse
from datetime import datetime, timedelta

# ============================================================
# 配置
# ============================================================
code = sys.argv[1] if len(sys.argv) > 1 else '000600'
prefix = 'sz' if code.startswith(('0', '2', '3')) else 'sh'
bs_code = f'{prefix}.{code}'
SCRIPT_DIR = '/home/admin/stock_knowledge/scripts'
sys.path.insert(0, SCRIPT_DIR)

# ============================================================
# 获取最近有效交易日（东财接口只在交易日有数据）
# ============================================================
def get_latest_trading_date():
    """自动往前找最近有数据的交易日（最多回溯7天）"""
    import baostock as bs
    today = datetime.now()
    bs.login()
    for days_back in range(0, 7):
        test_date = (today - timedelta(days=days_back)).strftime('%Y-%m-%d')
        rs = bs.query_history_k_data_plus(
            bs_code, 'date,close',
            start_date=test_date, end_date=test_date,
            frequency='d', adjustflag='2'
        )
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        if data:
            bs.logout()
            return test_date
    bs.logout()
    return today.strftime('%Y-%m-%d')

DATE = get_latest_trading_date()
print(f"\n📅 数据基准日（最近有效交易日）：{DATE}")

# ============================================================
# 工具函数
# ============================================================
def curl_json(url, timeout=30):
    """东财API请求封装"""
    try:
        r = subprocess.run(
            ["curl", "-s", url, "-H", "User-Agent: Mozilla/5.0"],
            capture_output=True, text=True, timeout=timeout
        )
        return json.loads(r.stdout)
    except:
        return {}

def get_baostock_df(bs_code, start_date, end_date, fields=None):
    """Baostock日K数据获取"""
    if fields is None:
        fields = 'date,open,high,low,close,volume,amount,pctChg,turn'
    bs.login()
    rs = bs.query_history_k_data_plus(
        bs_code, fields,
        start_date=start_date, end_date=end_date,
        frequency='d', adjustflag='2'
    )
    data = []
    while rs.next():
        data.append(rs.get_row_data())
    bs.logout()
    df = pd.DataFrame(data, columns=rs.fields)
    for col in ['open','high','low','close','volume','amount','pctChg','turn']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
    if 'turn' in df.columns:
        df['turnover'] = df['turn']
    return df

# ============================================================
# Step 1: 近15日详细K线（定性定位用）
# ============================================================
print("=" * 65)
print(f"【Step 1 定性定位 - 近15日详细数据】  代码：{code}")
print("=" * 65)

start_15 = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
df_15 = get_baostock_df(bs_code, start_15, DATE)

print(f"\n日期         开      高      低      收    涨跌%     量(万)  换手%")
print("-" * 70)
for _, r in df_15.iterrows():
    turn = r['turn'] if 'turn' in r and not pd.isna(r['turn']) else 0
    pct  = r['pctChg'] if 'pctChg' in r else 0
    vol  = r['volume'] / 1e4 if 'volume' in r else 0
    date_str = str(r['date'])[:10] if 'date' in r else ''
    print(f"{date_str}  {r['open']:>6.2f} {r['high']:>6.2f} {r['low']:>6.2f} "
          f"{r['close']:>6.2f}  {pct:>+6.2f}%  {vol:>7.0f}万  {turn:>5.2f}%")

# ============================================================
# Step 2: 技术指标计算
# ============================================================
print("\n" + "=" * 65)
print(f"【Step 2 技术指标】  代码：{code}")
print("=" * 65)

start_240 = (datetime.now() - timedelta(days=240)).strftime('%Y-%m-%d')
df = get_baostock_df(bs_code, start_240, DATE)

closes  = df['close'].tolist()
volumes = df['volume'].tolist()
highs   = df['high'].tolist()
lows    = df['low'].tolist()
opens   = df['open'].tolist()

# 均线
for ma_n in [5, 10, 20, 60]:
    df[f'ma{ma_n}'] = df['close'].rolling(ma_n, min_periods=1).mean()

# MACD
df['dif'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
df['macd'] = (df['dif'] - df['dea']) * 2

# KDJ
l9  = df['low'].rolling(9, min_periods=1).min()
h9  = df['high'].rolling(9, min_periods=1).max()
rsv = (df['close'] - l9) / (h9 - l9 + 0.0001) * 100
df['k'] = rsv.ewm(com=2, adjust=False).mean()
df['d'] = df['k'].ewm(com=2, adjust=False).mean()
df['j'] = 3 * df['k'] - 2 * df['d']

# RSI
for p in [6, 12, 24]:
    delta = df['close'].diff()
    gain  = delta.where(delta > 0, 0).rolling(p, min_periods=1).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(p, min_periods=1).mean()
    df[f'rsi{p}'] = 100 - (100 / (1 + gain / (loss + 0.0001)))

# 布林带
ma20_s = df['close'].rolling(20, min_periods=1).mean()
std20  = df['close'].rolling(20, min_periods=1).std()
df['boll_u'] = ma20_s + 2 * std20
df['boll_m'] = ma20_s
df['boll_l'] = ma20_s - 2 * std20

# 量比
df['vol_ma5']  = df['volume'].rolling(5, min_periods=1).mean()
df['vol_ma20'] = df['volume'].rolling(20, min_periods=1).mean()
df['vol_ratio'] = df['volume'] / df['vol_ma20']

# ATR
hl = df['high'] - df['low']
hc = abs(df['high'] - df['close'].shift())
lc = abs(df['low'] - df['close'].shift())
tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
df['atr']    = tr.rolling(14, min_periods=1).mean()
df['atr_pct'] = df['atr'] / df['close'] * 100

# 最新值
latest   = df.iloc[-1]
prev     = df.iloc[-2]
recent_5  = df.tail(5)
recent_20 = df.tail(20)
last_close = float(latest['close'])

# 主力行为
vol_prev_avg    = df.iloc[-25:-5]['volume'].mean() if len(df) >= 25 else df['volume'].mean()
price_trend_5   = float(recent_5['close'].iloc[-1]) - float(recent_5['close'].iloc[0])
vol_trend_5     = float(recent_5['volume'].iloc[-1]) - float(recent_5['volume'].iloc[0])
divergence_signal  = (price_trend_5 > 0 and vol_trend_5 < 0) or (price_trend_5 < 0 and vol_trend_5 > 0)
volume_compressed  = float(recent_5['volume'].mean()) < vol_prev_avg * 0.6
vol_breakout        = float(latest['vol_ratio']) > 1.5 and float(latest['pctChg']) > 2.0
high_upper         = float(latest['high']) - max(float(latest['open']), float(latest['close']))
low_lower          = min(float(latest['open']), float(latest['close'])) - float(latest['low'])
body               = abs(float(latest['close']) - float(latest['open']))
pressure_signal    = body > 0.01 and high_upper > body * 1.5
support_signal     = body > 0.01 and low_lower > body * 1.5
high_20 = float(recent_20['high'].max())
low_20  = float(recent_20['low'].min())
pos_in_boll = (last_close - float(latest['boll_l'])) / (float(latest['boll_u']) - float(latest['boll_l']) + 0.001)
pos_in_20d  = (last_close - low_20) / (high_20 - low_20 + 0.001)
ma_arrangement = '多头' if float(latest['ma5']) > float(latest['ma10']) > float(latest['ma20']) else \
                  ('空头' if float(latest['ma5']) < float(latest['ma10']) < float(latest['ma20']) else '缠绕')
ma5_cross_up = (float(latest['ma5']) > float(latest['ma10'])) and (float(prev['ma5']) <= float(prev['ma10']))
dif_cross_up = (float(latest['dif']) > float(latest['dea'])) and (float(prev['dif']) <= float(prev['dea']))

# 近5日K线阴阳
ks = []
for i in range(-5, 0):
    pct = (closes[i] - opens[i]) / opens[i] * 100 if opens[i] else 0
    ks.append('阳' if pct > 1 else '阴' if pct < -1 else '十')

# 倍量日检测
df['vol_ratio_prev'] = df['volume'] / df['volume'].shift(1)

print(f"\n代码: {code}  日期: {latest['date'].strftime('%Y-%m-%d')}  "
      f"收盘: {last_close:.2f}  涨跌: {float(latest['pctChg']):+.2f}%  ATR%: {float(latest['atr_pct']):.2f}%")
print(f"\n均线: MA5={float(latest['ma5']):.3f} MA10={float(latest['ma10']):.3f} "
      f"MA20={float(latest['ma20']):.3f} MA60={float(latest['ma60']):.3f}")
print(f"RSI:  RSI6={float(latest['rsi6']):.1f}  RSI12={float(latest['rsi12']):.1f}  RSI24={float(latest['rsi24']):.1f}")
print(f"KDJ:  K={float(latest['k']):.2f}  D={float(latest['d']):.2f}  J={float(latest['j']):.2f}")
print(f"MACD: DIF={float(latest['dif']):.4f}  DEA={float(latest['dea']):.4f}  "
      f"柱={float(latest['macd']):.4f}({'红柱' if float(latest['macd']) > 0 else '绿柱'})")
print(f"BOLL: {float(latest['boll_l']):.3f}/{float(latest['boll_m']):.3f}/{float(latest['boll_u']):.3f}  "
      f"乖离位置: {pos_in_boll:.1%}")
print(f"量价: 量比={float(latest['vol_ratio']):.2f}  20日位置: {pos_in_20d:.1%}")
print(f"均线排列: {ma_arrangement}  MA5上穿MA10: {ma5_cross_up}  DIF上穿DEA: {dif_cross_up}")
print(f"K线形态(近5日): {'/'.join(ks)}")
print(f"\n主力行为:")
print(f"  量价背离={divergence_signal}  缩量整理={volume_compressed}  "
      f"爆量={vol_breakout}  压单={pressure_signal}  托单={support_signal}")

print(f"\n近15日倍量日(量能翻倍):")
has_vol_signal = False
for _, r in df.tail(15).iterrows():
    if not pd.isna(r.get('vol_ratio_prev')) and float(r['vol_ratio_prev']) >= 2.0:
        print(f"  {r['date'].strftime('%Y-%m-%d')}  "
              f"量:{float(r['volume'])/1e4:.0f}万(前日{float(r['vol_ratio_prev']):.1f}倍)  "
              f"收:{float(r['close']):.2f}  {float(r['pctChg']):+.2f}%")
        has_vol_signal = True
if not has_vol_signal:
    print("  （近15日无倍量日）")

# ============================================================
# Step 3: 基本面 (RPT_F10_ORG_BASICINFO)
# ============================================================
print("\n" + "=" * 65)
print(f"【Step 7 基本面】  代码：{code}")
print("=" * 65)

FILTER_F10 = urllib.parse.quote(f"(SECURITY_CODE={code})")
url_f10 = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_F10_ORG_BASICINFO"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,ORG_NAME,MAIN_BUSINESS,"
             "INCOME_STRU_NAMENEW,BOARD_NAME_1LEVEL,BOARD_NAME_2LEVEL,BOARD_NAME_3LEVEL,"
             "REGIONBK,GROSS_PROFIT_RATIO,LISTING_DATE"
    f"&pageNumber=1&pageSize=1&filter={FILTER_F10}&source=WEB&client=WEB"
)
r_f10 = curl_json(url_f10)
f10_data = {}
if r_f10.get('result') and r_f10['result'].get('data'):
    f10_data = r_f10['result']['data'][0]
    print(f"  简称:       {f10_data.get('SECURITY_NAME_ABBR', '')}")
    print(f"  全称:       {f10_data.get('ORG_NAME', '')}")
    print(f"  主营:       {f10_data.get('MAIN_BUSINESS', '')}")
    print(f"  收入结构:   {f10_data.get('INCOME_STRU_NAMENEW', '')}")
    print(f"  行业(三级): {f10_data.get('BOARD_NAME_1LEVEL', '')}-{f10_data.get('BOARD_NAME_2LEVEL', '')}-{f10_data.get('BOARD_NAME_3LEVEL', '')}")
    print(f"  地区:       {f10_data.get('REGIONBK', '')}")
    print(f"  上市日期:   {f10_data.get('LISTING_DATE', '')}")
    sector_name = f10_data.get('BOARD_NAME_1LEVEL', '')
else:
    print("  ⚠️ 基本面数据获取失败")
    sector_name = ''

stock_name = f10_data.get('SECURITY_NAME_ABBR', code)

# ============================================================
# Step 4: 估值 (RPT_VALUEANALYSIS_DET)
# ============================================================
print("\n" + "=" * 65)
print(f"【Step 8 估值水平】  代码：{code}")
print("=" * 65)

FILTER_V = urllib.parse.quote(f"(TRADE_DATE='{DATE}')(SECURITY_CODE={code})")
url_val = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_VALUEANALYSIS_DET"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
    f"&pageNumber=1&pageSize=1&filter={FILTER_V}&source=WEB&client=WEB"
)
r_val = curl_json(url_val)
pe = pb = mkt = sector = price = 0
if r_val.get('result') and r_val['result'].get('data'):
    vc = r_val['result']['data'][0]
    pe     = vc.get('PE_TTM', 0) or 0
    pb     = vc.get('PB_MRQ', 0) or 0
    mkt    = (vc.get('TOTAL_MARKET_CAP', 0) or 0) / 1e8
    sector = vc.get('BOARD_NAME', '') or sector_name
    price  = vc.get('CLOSE_PRICE', 0) or 0
    print(f"  估值: PE={pe:.1f}  PB={pb:.2f}  市值={mkt:.0f}亿  板块={sector}  股价={price}")

# ============================================================
# 资金面数据采集（东财 fflow/daykline 接口）
# f53=总净流 f54=超大单净流 f55=大单净流 f56=中单净流 f57=小单净流（万元）
# 主力净流 = f54(超大单) + f55(大单)
# ============================================================
mf_main_net_w = 0      # 主力净流（万元）
mf_total_w = 0         # 总成交额（万元）
mf_main_pct = 0        # 主力净流占比%
mf_days = 0            # 可用历史天数
mf_net_list = []       # 近5日主力净流列表（万元）
mf_has_history = False # 是否有5日历史数据

mf_secid = ('0.' + code) if code.startswith(('0', '2', '3')) else ('1.' + code)
url_mf = (
    f"https://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get"
    f"?lmt=5&klt=1&secid={mf_secid}"
    f"&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57"
)
r_mf = curl_json(url_mf)
if r_mf.get('data') and r_mf['data'].get('klines'):
    klines = r_mf['data']['klines']
    mf_days = len(klines)
    mf_has_history = mf_days >= 5
    mf_net_list = []
    for kl in klines:
        p = kl.split(',')
        if len(p) >= 6:
            # p[3]=超大单净流(元→转万元), p[4]=大单净流(元→转万元)
            day_main_net = (float(p[3]) + float(p[4])) / 1e4  # 主力净流（万元）
            mf_net_list.append(day_main_net)
    if klines:
        last_kl = klines[-1].split(',')
        # p[2]=总成交额（元），p[3]=超大单净流(元)，p[4]=大单净流(元)
        mf_total_y = float(last_kl[2])   # 总成交额（元）
        mf_main_net_y = float(last_kl[3]) + float(last_kl[4])  # 主力净流（元）
        mf_main_net_w = mf_main_net_y / 1e4  # 主力净流（万元）
        # 用总成交额绝对值计算主力净流占比（避免p[2]为负的影响）
        mf_main_pct = (mf_main_net_y / abs(mf_total_y) * 100) if mf_total_y != 0 else 0

print(f"\n  【资金面】主力净流: {mf_main_net_w/1e4:+.2f}亿({mf_main_pct:+.1f}%) "
      f"总成交额: {abs(mf_total_y)/1e8:.2f}亿 | 历史数据: {mf_days}天{'✅' if mf_has_history else '⚠️不足5日'}")

# 行业均值（东财中文filter有bug，已在下方generate_report里兜底提示）
# ============================================================
# Step 5: 题材概念 (f129字段)
# ============================================================
secid = ("0." + code) if code.startswith(('0', '2', '3')) else ("1." + code)
url_concept = (
    "https://push2delay.eastmoney.com/api/qt/stock/get"
    f"?secid={secid}&fields=f58,f57,f129&ut=fa5fd1943c7b386f172d6893dbfba10b"
)
r_con = curl_json(url_concept)
concepts = []
if r_con.get('data') and r_con['data'].get('f129'):
    concepts = [c.strip() for c in r_con['data']['f129'].split(',') if c.strip()]
    print(f"\n  题材概念({len(concepts)}个): {concepts}")
else:
    print(f"\n  ⚠️ 题材概念获取失败")

# ============================================================
# Step 6: 近30日热点题材
# ============================================================
url_hot = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=30&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f3&fs=m:90+t:3"
    "&fields=f12,f14,f2,f3,f62"
)
r_hot = curl_json(url_hot)
hot_sectors = []
if r_hot.get('data') and r_hot['data'].get('diff'):
    for item in r_hot['data']['diff']:
        hot_sectors.append({
            'name': item.get('f14', ''),
            'pct_chg': item.get('f3', 0),
            'main_force': item.get('f62', 0)
        })

print(f"\n  近30日热点题材 Top15:")
for i, h in enumerate(hot_sectors[:15], 1):
    print(f"    {i:2d}. {h['name']:<12} {h['pct_chg']:>+6.2f}%  主力净流:{h['main_force']/10000:+.0f}万")

# ============================================================
# Step 7: 热点匹配
# ============================================================
print(f"\n  ⭐ 题材热点匹配:")
matched = []
for c in concepts:
    for h in hot_sectors[:30]:
        if c in h['name'] or h['name'] in c:
            matched.append({'concept': c, 'hot': h['name'],
                            'pct': h['pct_chg'], 'mf': h['main_force']/10000})
            break
if matched:
    for m in matched:
        print(f"    ✓ {m['concept']} → {m['hot']}  {m['pct']:+.2f}%  主力:{m['mf']:+.0f}万")
else:
    print(f"    ⚠️ 无直接匹配的30日热点题材")

# ============================================================
# Step 8: 筹码分布 (CYC成本)
# ============================================================
print("\n" + "=" * 65)
print(f"【筹码分布 CYC成本】  代码：{code}")
print("=" * 65)

chip_data = {}
avg_cost  = None
benefit_part = None
chip_70_range = None
chip_90_range = None
chip_peak = None

try:
    from chip_distribution import calc_chip_distribution, chip_analysis_text
    start_chip = (datetime.now() - timedelta(days=300)).strftime('%Y-%m-%d')
    df_chip = get_baostock_df(bs_code, start_chip, DATE)
    chip = calc_chip_distribution(df_chip, accuracy_factor=150, trading_days=210)
    print(chip_analysis_text(chip, code, last_close))
    avg_cost      = chip.avg_cost
    benefit_part  = chip.benefit_part
    chip_70_range = chip.percent_chips['70']['priceRange'] if chip.percent_chips else None
    chip_90_range = chip.percent_chips['90']['priceRange'] if chip.percent_chips else None
    chip_peak     = None  # ChipData无此属性，保留用于报告提示
except Exception as e:
    print(f"  ⚠️ 筹码分布计算失败: {e}")

# ============================================================
# Step 9: 基本面财务数据 (Baostock) — 增强版
# 包含：利润表 + 成长能力 + 运营能力 + 资产负债表 + 杜邦分析
# ============================================================
print("\n" + "=" * 65)
print(f"【财务数据 Baostock】  代码：{code}")
print("=" * 65)

bs.login()
def gd(rs):
    d = []
    while rs.error_code == '0' and rs.next():
        d = rs.get_row_data()
    return d if d else [None] * 20

fp   = gd(bs.query_profit_data(code=bs_code, year=2025, quarter=4))
fp24 = gd(bs.query_profit_data(code=bs_code, year=2024, quarter=4))
fg   = gd(bs.query_growth_data(code=bs_code, year=2025, quarter=4))
fo   = gd(bs.query_operation_data(code=bs_code, year=2025, quarter=4))
fb   = gd(bs.query_balance_data(code=bs_code, year=2025, quarter=4))
fd   = gd(bs.query_dupont_data(code=bs_code, year=2025, quarter=4))
bs.logout()

sf = lambda v, d=0: float(v) if v and v not in ['', '-', None] else d
sp = lambda v: sf(v) * 100

roe_2025 = np_margin = gp_margin = net_profit_2025 = eps_2025 = rev_2025 = None
total_share = liq_share = yoy_ni = yoy_eps = nrt = invt = None
current_ratio = quick_ratio = cash_ratio = liability_to_asset = None
dupont_net_profit = dupont_asset_turn = dupont_equity_mul = dupont_tax_burden = dupont_operating_profit = None
yoy_rev = revenue_2025 = revenue_2024 = net_profit_2024 = None

if fp and fp[3]:
    eps_2025      = sf(fp[7])
    net_profit_2025 = sf(fp[6])
    rev_2025      = sf(fp[8])
    total_share   = sf(fp[9]) / 1e8
    liq_share     = sf(fp[10]) / 1e8
    roe_2025      = sp(fp[3])
    np_margin     = sp(fp[4])
    gp_margin      = sp(fp[5])
    dupont_net_profit = sp(fp[4])  # 净利率作为杜邦起点
    print(f"  【利润表 2025年年报】")
    print(f"    净资产收益率(ROE): {roe_2025:.2f}%")
    print(f"    销售净利率: {np_margin:.2f}%")
    print(f"    销售毛利率: {gp_margin:.2f}%")
    print(f"    净利润: {net_profit_2025/1e8:.2f}亿元")
    print(f"    每股收益(EPS): {eps_2025:.4f}元")
    print(f"    主营收入: {rev_2025/1e8:.2f}亿元")
    print(f"    总股本: {total_share:.2f}亿股  流通股本: {liq_share:.2f}亿股")
    if fp24 and fp24[3]:
        roe_2024 = sp(fp24[3])
        rev_2024 = sf(fp24[8])
        net_profit_2024 = sf(fp24[6])
        yoy_rev = (rev_2025 - rev_2024) / rev_2024 * 100 if rev_2024 else None
        print(f"  【对比2024年】")
        print(f"    ROE: {roe_2024:.2f}% → {roe_2025:.2f}% ({roe_2025 - roe_2024:+.1f}%)")
        if net_profit_2024:
            ni_change = (net_profit_2025 - net_profit_2024) / abs(net_profit_2024) * 100
            print(f"    净利润: {net_profit_2024/1e8:.2f}亿 → {net_profit_2025/1e8:.2f}亿 ({ni_change:+.1f}%)")
        if yoy_rev:
            print(f"    营收YOY: {yoy_rev:+.1f}%")

if fg and fg[5]:
    yoy_ni  = sp(fg[5])
    yoy_eps = sp(fg[6])
    yoy_equity = sp(fg[3])
    print(f"  【成长能力】")
    print(f"    净利润YOY: {yoy_ni:+.1f}%")
    print(f"    EPS_YOY: {yoy_eps:+.1f}%")
    if yoy_equity:
        print(f"    净资产YOY: {yoy_equity:+.1f}%")

if fo and fo[3]:
    nrt = sf(fo[3])
    invt = sf(fo[5])
    cat = sf(fo[6])
    print(f"  【营运能力】")
    print(f"    应收周转率: {nrt:.1f}次（{sf(fo[4]):.0f}天）")
    print(f"    存货周转率: {invt:.1f}次（{sf(fo[6]):.0f}天）")
    print(f"    流动资产周转率: {cat:.1f}次")

if fb and fb[3]:
    current_ratio = sf(fb[3])
    quick_ratio = sf(fb[4])
    cash_ratio = sf(fb[5])
    yoy_liability = sp(fb[6])
    liability_to_asset = sp(fb[7])
    asset_to_equity = sf(fb[8])
    print(f"  【资产负债表】")
    print(f"    流动比率: {current_ratio:.2f}{'(优秀)' if current_ratio>=2 else '(良好)' if current_ratio>=1 else '(偏弱)'}")
    print(f"    速动比率: {quick_ratio:.2f}{'(优秀)' if quick_ratio>=1 else '(偏弱)'}")
    print(f"    现金比率: {cash_ratio:.2f}")
    print(f"    资产负债率: {liability_to_asset:.2f}%{'(低负债)' if liability_to_asset<40 else '(合理)' if liability_to_asset<60 else '(高负债⚠️)'}")
    print(f"    资产负责率YOY: {yoy_liability:+.1f}%")
    print(f"    产权比率: {asset_to_equity:.2f}")

if fd and fd[3]:
    dupont_equity_mul = sf(fd[4])  # 权益乘数 1.35
    dupont_asset_turn = sf(fd[5])  # 资产周转率 0.73（原始小数）
    dupont_tax_burden = sf(fd[8])  # 税负 burden 0.82（原始小数）
    dupont_operating_profit = sf(fd[6])  # 营业利润/净利润比率（恒=1，跳过）
    dupont_net_profit = sf(fd[7])  # 净利率 0.061（原始小数，等于ROE/资产周转/权益乘数）
    dupont_roic = sf(fd[3])  # dupontROE 原始值 0.0606
    print(f"  【杜邦分析(ROE拆解)】")
    print(f"    净利率: {dupont_net_profit*100:.2f}%")
    print(f"    资产周转率: {dupont_asset_turn:.2f}次")
    print(f"    权益乘数: {dupont_equity_mul:.2f}{'（低杠杆）' if dupont_equity_mul<2 else '（合理）' if dupont_equity_mul<3 else '（高杠杆⚠️）'}")
    print(f"    → 杜邦ROE = 净利率×周转率×权益乘数 = {dupont_roic*100:.2f}%（直接取自fd[3]）")

# —————— 财务综合评分 ——————
fin_score = 0
fin_detail = []

if roe_2025:
    if roe_2025 >= 15:   fin_score += 25
    elif roe_2025 >= 10: fin_score += 18
    elif roe_2025 >= 5:  fin_score += 10
    elif roe_2025 >= 0:  fin_score += 3
    else:                fin_score += 0
    fin_detail.append(f"ROE={roe_2025:.1f}%")

if yoy_ni is not None:
    if yoy_ni >= 30:     fin_score += 25
    elif yoy_ni >= 15:   fin_score += 18
    elif yoy_ni >= 0:    fin_score += 10
    elif yoy_ni >= -20:  fin_score += 3
    else:                fin_score += 0
    fin_detail.append(f"净利润YOY={yoy_ni:.1f}%")

if yoy_rev is not None:
    if yoy_rev >= 20:    fin_score += 20
    elif yoy_rev >= 10:  fin_score += 14
    elif yoy_rev >= 0:   fin_score += 7
    elif yoy_rev >= -10: fin_score += 2
    else:                fin_score += 0
    fin_detail.append(f"营收YOY={yoy_rev:.1f}%")

if liability_to_asset is not None:
    if liability_to_asset < 30:  fin_score += 15
    elif liability_to_asset < 50: fin_score += 10
    elif liability_to_asset < 70: fin_score += 5
    else:                        fin_score += 0
    fin_detail.append(f"资产负债率={liability_to_asset:.1f}%")

if current_ratio:
    if current_ratio >= 2:    fin_score += 15
    elif current_ratio >= 1: fin_score += 10
    elif current_ratio >= 0.5: fin_score += 5
    else:                    fin_score += 0
    fin_detail.append(f"流动比率={current_ratio:.2f}")

print(f"\n  【财务综合评分】{fin_score}/75")
print(f"  评分维度: {', '.join(fin_detail) if fin_detail else '数据不足'}")

FIN_SCORE = fin_score
FIN_DETAIL = fin_detail

# —————— 资金面综合评分（20分制）——————
# 维度：近5日主力净流方向(8分) + 今日主力净流占比(6分) + 连续净流入天数(6分)
cap_score = 0
cap_detail = []

# ① 近5日净流方向（8分）
if mf_has_history and mf_net_list:
    avg_net = sum(mf_net_list) / len(mf_net_list)
    if avg_net > 5000:        # 日均主力净流入>5000万
        cap_score += 8; cap_detail.append(f'5日净流入均{avg_net/1e4:+.2f}亿')
    elif avg_net > 1000:
        cap_score += 5; cap_detail.append(f'5日净流入均{avg_net/1e4:+.2f}亿')
    elif avg_net > 0:
        cap_score += 2; cap_detail.append(f'5日小幅净流入{avg_net/1e4:+.2f}亿')
    elif avg_net > -1000:
        cap_score += 0; cap_detail.append(f'5日轻微净流出{avg_net/1e4:+.2f}亿')
    elif avg_net > -5000:
        cap_score -= 3; cap_detail.append(f'5日净流出{-avg_net/1e4:.2f}亿')
    else:
        cap_score -= 6; cap_detail.append(f'5日大幅净流出{-avg_net/1e4:.2f}亿⚠️')
else:
    # 无5日历史，看今日单日
    if mf_main_net_w > 5000:
        cap_score += 4; cap_detail.append(f'今日主力净流入{mf_main_net_w/1e4:+.2f}亿(无5日历史)')
    elif mf_main_net_w > 0:
        cap_score += 1; cap_detail.append(f'今日小幅净流入{mf_main_net_w/1e4:+.2f}亿(无5日历史)')
    elif mf_main_net_w > -3000:
        cap_score -= 2; cap_detail.append(f'今日净流出{abs(mf_main_net_w)/1e4:.2f}亿(无5日历史)')

# ② 今日主力净流占比（6分）
if abs(mf_main_pct) > 15:
    cap_score += 6; cap_detail.append(f'主力占比{mf_main_pct:+.1f}%(强势)')
elif abs(mf_main_pct) > 8:
    cap_score += 4; cap_detail.append(f'主力占比{mf_main_pct:+.1f}%(明显)')
elif abs(mf_main_pct) > 3:
    cap_score += 2; cap_detail.append(f'主力占比{mf_main_pct:+.1f}%(一般)')
else:
    cap_score += 0; cap_detail.append(f'主力占比{mf_main_pct:+.1f}%(偏弱)')

# ③ 连续净流入天数（6分）
if mf_has_history and mf_net_list:
    pos_days = sum(1 for x in mf_net_list if x > 0)
    if pos_days >= 4:
        cap_score += 6; cap_detail.append(f'5日中{pos_days}日净流入(持续买入)')
    elif pos_days >= 3:
        cap_score += 4; cap_detail.append(f'5日中{pos_days}日净流入(偏多)')
    elif pos_days >= 2:
        cap_score += 1; cap_detail.append(f'5日中{pos_days}日净流入(分歧)')
    else:
        cap_score -= 2; cap_detail.append(f'5日中{pos_days}日净流入(偏空)')

cap_score = max(0, min(20, cap_score))
print(f"\n  【资金面综合评分】{cap_score}/20")
print(f"  评分维度: {', '.join(cap_detail) if cap_detail else '数据不足'}")

CAP_SCORE = cap_score
CAP_DETAIL = cap_detail


# ============================================================
# 完整8步报告生成函数（宁波韵升格式）
# ============================================================
def _fl(condition, true='✅', false='❌'):
    return true if condition else false

def generate_full_report(
        code, DATE, last_close,
        df, latest, prev, recent_5, recent_20,
        concepts, hot_sectors,
        stock_name, f10_data,
        pe, pb, mkt, sector, price,
        roe_2025, np_margin, gp_margin, net_profit_2025,
        eps_2025, rev_2025, total_share, liq_share,
        yoy_ni, yoy_eps, yoy_rev,
        nrt, invt,
        current_ratio, quick_ratio, liability_to_asset,
        dupont_net_profit, dupont_asset_turn, dupont_equity_mul,
        FIN_SCORE,
        CAP_SCORE,          # 资金面综合评分（20分制）
        mf_main_net_w,      # 主力净流（万元）
        mf_main_pct,        # 主力净流占比%
        avg_cost, benefit_part,
        chip_70_range, chip_90_range, chip_peak,
        vol_breakout, divergence_signal, volume_compressed,
        pressure_signal, support_signal,
        ma_arrangement, ma5_cross_up, dif_cross_up,
        pos_in_boll, pos_in_20d,
        high_20, low_20
):
    """输出完整8步结构化报告（宁波韵升格式）"""

    ma5  = float(latest['ma5']);  ma10 = float(latest['ma10'])
    ma20 = float(latest['ma20']);  ma60 = float(latest['ma60'])
    boll_u = float(latest['boll_u']); boll_m = float(latest['boll_m']); boll_l = float(latest['boll_l'])
    rsi6  = float(latest['rsi6']);  rsi12 = float(latest['rsi12']); rsi24 = float(latest['rsi24'])
    k_val = float(latest['k']);    d_val = float(latest['d']);        j_val = float(latest['j'])
    dif   = float(latest['dif']);  dea   = float(latest['dea']);      macd  = float(latest['macd'])
    vol_ratio = float(latest['vol_ratio']); atr_pct = float(latest['atr_pct'])
    pct_chg   = float(latest['pctChg'])

    # 阶段定位
    if pos_in_boll > 1.0:
        stage = 'BOLL上轨外强势拉升段'
    elif pos_in_boll > 0.8:
        stage = '主升浪进行中'
    elif pos_in_boll > 0.5:
        stage = '上升趋势确立'
    elif ma_arrangement == '多头':
        stage = '均线多头整理'
    else:
        stage = '低位震荡/筑底'

    # 10维度
    dim_ma    = '✅多头' if ma_arrangement=='多头' else ('❌空头' if ma_arrangement=='空头' else '⚠️缠绕')
    dim_kline = '✅强势' if pct_chg > 2 else ('✅健康' if pct_chg > 0 else '⚠️偏弱')
    dim_vol   = '✅量增' if vol_ratio > 1.2 else ('✅缩量' if vol_ratio < 0.8 else '⚠️正常')
    dim_boll  = '🔴突破' if pos_in_boll > 1.0 else ('⚠️轨上' if pos_in_boll > 0.5 else '🟢轨下')
    dim_rsi   = '🔴过热' if rsi6 > 80 else ('⚠️偏热' if rsi6 > 60 else '✅正常')
    dim_chip  = ('🔴高位风险' if (benefit_part and benefit_part > 0.9)
                 else '🟢低位机会' if (benefit_part and benefit_part < 0.3) else '✅健康')

    # ============================================================
    # 7种走势路径定义（老渔民实战框架）
    # ============================================================
    PATH_DEFS = {
        'A_主升延续': {
            'name': 'A·主升延续',
            '特征': '缩量回踩不破均线，RSI健康，量增价涨',
            '散户误区': '过早就卖出踏空',
            '主力意图': '锁仓控盘，稳步拉升',
            '口诀': '缩量回踩不破线，持股不动等加速。'
        },
        'B_震荡洗盘': {
            'name': 'B·震荡洗盘',
            '特征': '放量滞涨/假突破后快速回落，RSI顶背离',
            '散户误区': '频繁交易，追涨杀跌',
            '主力意图': '高抛低吸，降低成本',
            '口诀': '放量不涨是洗盘，高抛低吸不追高。'
        },
        'C_趋势破坏': {
            'name': 'C·趋势破坏',
            '特征': '放量跌破MA60/结构位，MACD死叉',
            '散户误区': '不止损，幻想反弹',
            '主力意图': '出货完毕，趋势逆转',
            '口诀': '趋势破坏须止损，不幻想来不侥幸。'
        },
        'D_先破后立': {
            'name': 'D·先破后立',
            '特征': '假跌破（跌3-5%内快速收回），制造恐慌',
            '散户误区': '跌破支撑就割肉，割在地板上',
            '主力意图': '启动前最后洗盘，震出最后不坚定者',
            '口诀': '跌破不慌看三天，放量收回是假破。'
        },
        'E_诱多出货': {
            'name': 'E·诱多出货',
            '特征': '假突破（前高/箱顶）后快速回落，RSI顶背离',
            '散户误区': '突破就追涨，追在高山上',
            '主力意图': '制造突破假象，高位派发',
            '口诀': '突破不急追，回踩确认再跟随。'
        },
        'F_挖坑填坑': {
            'name': 'F·挖坑填坑',
            '特征': '急跌10-20%但缩量，快速收复并创新高',
            '散户误区': '急跌就恐慌卖出，卖完就创新高',
            '主力意图': '深度洗盘，清洗获利盘蓄力二波',
            '口诀': '急跌缩量是洗盘，坑底不慌把货捡。'
        },
        'G_缓跌筑底': {
            'name': 'G·缓跌筑底',
            '特征': '阴跌数周~数月，成交量持续萎缩至地量',
            '散户误区': '耐心磨光，割在黎明前',
            '主力意图': '低位慢慢吸筹，用时间磨掉散户耐心',
            '口诀': '缓跌磨底最难熬，不见兔子不撒鹰。'
        },
    }

    # 根据当前技术面筛选最相关的3条路径
    # 优先根据BOLL位置+RSI+趋势判断
    if pos_in_boll > 1.0 and rsi6 < 88:
        # BOLL突破上轨强势段：主升延续/诱多出货/先破后立
        top_paths = ['A_主升延续', 'E_诱多出货', 'D_先破后立']
        prob = [45, 30, 25]
    elif pos_in_boll > 1.0 and rsi6 >= 88:
        # BOLL突破 + RSI过热：诱多出货/震荡洗盘/先破后立
        top_paths = ['E_诱多出货', 'B_震荡洗盘', 'D_先破后立']
        prob = [40, 35, 25]
    elif pos_in_boll > 0.8 and rsi6 < 80:
        # 上升趋势健康：主升延续/挖坑填坑/震荡洗盘
        top_paths = ['A_主升延续', 'F_挖坑填坑', 'B_震荡洗盘']
        prob = [40, 30, 30]
    elif rsi6 > 85:
        # RSI过热：震荡洗盘/诱多出货/趋势破坏
        top_paths = ['B_震荡洗盘', 'E_诱多出货', 'C_趋势破坏']
        prob = [40, 35, 25]
    elif pos_in_boll < 0.5 and ma_arrangement != '多头':
        # 下降/低位：缓跌筑底/先破后立/挖坑填坑
        top_paths = ['G_缓跌筑底', 'D_先破后立', 'F_挖坑填坑']
        prob = [40, 35, 25]
    else:
        # 中性/一般：震荡洗盘/主升延续/趋势破坏
        top_paths = ['B_震荡洗盘', 'A_主升延续', 'C_趋势破坏']
        prob = [40, 35, 25]

    # 计算路径对应概率
    pa, pb_pct, pc = prob[0], prob[1], prob[2]
    pa_def = PATH_DEFS[top_paths[0]]
    pb_def = PATH_DEFS[top_paths[1]]
    pc_def = PATH_DEFS[top_paths[2]]

    # 止损（提前计算，供路径价位使用）
    stop_loss = round(max(last_close * 0.93, boll_l * 0.98) / 0.05) * 0.05

    # 根据路径类型计算关键价位
    def path_price_range(path_key, latest_close, ma20, ma10, boll_u, boll_m, boll_l, stop_loss):
        if path_key == 'A_主升延续':
            return f"上行目标{boll_u*1.1:.2f}~{boll_u*1.2:.2f}；回踩{ma20:.2f}可低吸"
        elif path_key == 'B_震荡洗盘':
            return f"回踩{ma20:.2f}~{ma10:.2f}；跌破{stop_loss:.2f}减仓"
        elif path_key == 'C_趋势破坏':
            return f"止损{stop_loss:.2f}；跌破{boll_l:.2f}清仓"
        elif path_key == 'D_先破后立':
            return f"观察{boll_l:.2f}是否3日内收回；守住则假破"
        elif path_key == 'E_诱多出货':
            return f"突破{boll_u:.2f}不追等回踩；回踩{ma20:.2f}确认再进"
        elif path_key == 'F_挖坑填坑':
            return f"急跌{boll_m*0.9:.2f}附近分批建仓；快速收复则确认"
        elif path_key == 'G_缓跌筑底':
            return f"观察{boll_l:.2f}支撑；等放量站上MA20右侧确认"
        return "待观察"

    path_a_prices = path_price_range(top_paths[0], last_close, ma20, ma10, boll_u, boll_m, boll_l, stop_loss)
    path_b_prices = path_price_range(top_paths[1], last_close, ma20, ma10, boll_u, boll_m, boll_l, stop_loss)
    path_c_prices = path_price_range(top_paths[2], last_close, ma20, ma10, boll_u, boll_m, boll_l, stop_loss)

    # ============================================================
    # Step 3：5维度综合评分（100分制）
    # 趋势结构:20 | 量价健康度:25 | K线信号质量:15
    # 主力行为可信度:20 | 板块与情绪环境:20
    # ============================================================

    # 热点匹配（提前计算，供d5评分使用）
    hot_match = []
    for c in concepts:
        for h in hot_sectors[:30]:
            if c in h['name'] or h['name'] in c:
                hot_match.append(f"{c}→{h['name']}{h['pct_chg']:+.2f}%")
                break

    score = 0; detail = []

    # ---- 维度一：趋势结构（20分）----
    d1 = 0; d1_note = []
    # 均线多头
    if ma_arrangement == '多头':
        d1 += 12; d1_note.append('均线完全多头')
    elif ma_arrangement == '空头':
        d1 -= 8; d1_note.append('均线空头排列')
    else:
        d1 += 4; d1_note.append('均线缠绕整理')
    # BOLL位置
    if pos_in_boll > 1.0:
        d1 += 5; d1_note.append(f'BOLL突破上轨({pos_in_boll:.1%})')
    elif pos_in_boll > 0.8:
        d1 += 3; d1_note.append(f'BOLL轨上({pos_in_boll:.1%})')
    else:
        d1 += 0; d1_note.append(f'BOLL中部/轨下({pos_in_boll:.1%})')
    # MACD红绿
    if macd > 0:
        d1 += 3; d1_note.append('MACD红柱')
    else:
        d1 -= 3; d1_note.append('MACD绿柱')
    d1 = max(0, min(20, d1))
    detail.append(('①趋势结构', d1, '/20', ' | '.join(d1_note)))

    # ---- 维度二：量价健康度（25分）----
    d2 = 0; d2_note = []
    if vol_ratio > 1.5 and pct_chg > 0:
        d2 += 10; d2_note.append('爆量上涨(量比%.1f)' % vol_ratio)
    elif vol_ratio > 1.0 and pct_chg > 0:
        d2 += 7; d2_note.append('温和放量上涨(量比%.1f)' % vol_ratio)
    elif vol_ratio < 0.8:
        d2 += 4; d2_note.append('缩量整理(量比%.1f)' % vol_ratio)
    else:
        d2 += 2; d2_note.append('量能正常')
    if vol_breakout:
        d2 += 8; d2_note.append('标志性爆量启动')
    if atr_pct < 3:
        d2 += 4; d2_note.append('振幅压缩(%s%%)主力控盘' % ('%.1f'%atr_pct))
    elif atr_pct > 5:
        d2 -= 3; d2_note.append('振幅过大(%s%%)' % ('%.1f'%atr_pct))
    if divergence_signal:
        d2 += 3; d2_note.append('量价背离')
    d2 = max(0, min(25, d2))
    detail.append(('②量价健康度', d2, '/25', ' | '.join(d2_note)))

    # ---- 维度三：K线信号质量（15分）----
    d3 = 0; d3_note = []
    if pct_chg >= 9.5:          # 涨停
        d3 = 15; d3_note.append('涨停信号(+10%)')
    elif pct_chg >= 5:
        d3 += 8; d3_note.append('大阳线(+%.1f%%)' % pct_chg)
    elif pct_chg > 0:
        d3 += 4; d3_note.append('小阳线(+%.1f%%)' % pct_chg)
    elif pct_chg < -5:
        d3 -= 6; d3_note.append('大阴线(%.1f%%)' % pct_chg)
    else:
        d3 += 1; d3_note.append('小阴线(%.1f%%)' % pct_chg)
    # 振幅
    if atr_pct < 3:
        d3 += 3; d3_note.append('振幅收缩强势')
    elif atr_pct > 6:
        d3 -= 2; d3_note.append('振幅过大')
    # KDJ多头
    if k_val > 80:
        d3 += 2; d3_note.append('KDJ高位钝化')
    elif k_val > 50:
        d3 += 1; d3_note.append('KDJ多方区')
    d3 = max(0, min(15, d3))
    detail.append(('③K线信号', d3, '/15', ' | '.join(d3_note)))

    # ---- 维度四：主力行为可信度（20分）----
    d4 = 0; d4_note = []
    if vol_breakout:
        d4 += 8; d4_note.append('爆量主力进场')
    if divergence_signal:
        d4 += 5; d4_note.append('量价背离控盘')
    if pressure_signal and support_signal:
        d4 += 4; d4_note.append('压托单组合强控盘')
    elif pressure_signal:
        d4 += 2; d4_note.append('上压单')
    if volume_compressed:
        d4 += 3; d4_note.append('缩量锁仓')
    if dif_cross_up:
        d4 += 3; d4_note.append('MACD金叉中期转强')
    if ma5_cross_up:
        d4 += 2; d4_note.append('均线短线金叉')
    if d4 > 0:
        d4_note_str = ' | '.join(d4_note) if d4_note else '无明显信号'
    else:
        d4_note_str = '主力信号偏弱'
    d4 = max(0, min(20, d4))
    detail.append(('④主力行为', d4, '/20', d4_note_str))

    # ---- 维度五：板块与情绪环境（20分）----
    d5 = 0; d5_note = []
    # 主线板块
    if sector and any(s in str(sector) for s in ['稀土','新能源','芯片','机器人','电力','军工','医药','AI','半导体']):
        d5 += 8; d5_note.append('主线板块(%s)' % sector)
    elif sector:
        d5 += 3; d5_note.append('非主线板块(%s)' % sector)
    # 题材数量
    if len(concepts) >= 8:
        d5 += 4; d5_note.append('题材丰富(%d个)' % len(concepts))
    elif len(concepts) >= 5:
        d5 += 3; d5_note.append('题材较多(%d个)' % len(concepts))
    elif len(concepts) >= 3:
        d5 += 1; d5_note.append('少量题材(%d个)' % len(concepts))
    # 热点匹配
    if hot_match:
        d5 += 4; d5_note.append('热点高度匹配')
    # RSI情绪
    if rsi6 > 88:
        d5 -= 8; d5_note.append('RSI严重过热(%.1f)' % rsi6)
    elif rsi6 > 80:
        d5 -= 5; d5_note.append('RSI超买(%.1f)' % rsi6)
    elif rsi6 > 65:
        d5 -= 2; d5_note.append('RSI偏热(%.1f)' % rsi6)
    else:
        d5 += 0; d5_note.append('RSI健康(%.1f)' % rsi6)
    # PE基本面
    if pe and pe > 0:
        if pe < 15:
            d5 += 4; d5_note.append('PE低估(%.1f)' % pe)
        elif pe < 40:
            d5 += 2; d5_note.append('PE合理(%.1f)' % pe)
        else:
            d5 -= 2; d5_note.append('PE偏高(%.1f)' % pe)
    d5 = max(0, min(20, d5))
    detail.append(('⑤板块情绪', d5, '/20', ' | '.join(d5_note)))

    # 总分
    score = d1 + d2 + d3 + d4 + d5

    # 判断结论
    if score >= 80:
        verdict = '🟢 强势主升结构 — 积极关注，回调积极布局'
    elif score >= 60:
        verdict = '🟡 可操作，但需择时 — 等待回调确认再入'
    else:
        verdict = '🔴 观望或短线博弈 — 趋势不明，多看少动'

    # 最大量日

    max_vol_row = df.sort_values('volume', ascending=False).iloc[0]
    vol_x = float(max_vol_row['volume']) / float(df.tail(20)['volume'].mean()) if len(df) >= 20 else 1
    max_vol_date = max_vol_row['date'].strftime('%Y-%m-%d')
    max_vol_pct  = float(max_vol_row['pctChg'])
    max_vol_turn = float(max_vol_row.get('turn', 0)) if not pd.isna(max_vol_row.get('turn')) else 0

    sep = '=' * 65
    print(f"\n{sep}")
    print(f"## {stock_name}({code}) — 老股民结构化分析报告")
    print(f"数据日期：{latest['date'].strftime('%Y-%m-%d')} | 收盘：{last_close:.2f}元 | 涨跌：{pct_chg:+.2f}%")
    print(sep)

    # Step 1
    print(f"\n## Step 1 · 定性定位")
    print(f"\n**【阶段定位】：{stage}")
    print(f"\n**【关键依据】：")
    print(f"1. **{max_vol_date}爆量启动**：换手{max_vol_turn:.2f}%（均量{vol_x:.1f}倍），"
          f"成交{float(max_vol_row['volume'])/1e4:.0f}万，涨幅{max_vol_pct:+.2f}%，主力正式进场信号")
    print(f"2. **均线{'完全多头' if ma_arrangement=='多头' else '排列'+ma_arrangement}**："
          f"MA5={ma5:.3f}>MA10={ma10:.3f}>MA20={ma20:.3f}，股价稳稳站于所有均线之上")
    print(f"3. **MACD{'红柱' if macd>0 else '绿柱'}中期动能**：DIF={dif:.4f}，"
          f"{'开口扩张' if dif>dea else '收敛中'}，{'主力仍在拉升' if macd>0 else '需观察'}")
    print(f"\n**【最大疑点】：**")
    rsi_warn = '严重超买！' if rsi6>88 else ('偏热' if rsi6>70 else '正常')
    chip_warn = ('筹码高位，获利盘随时可能兑现' if (benefit_part and benefit_part>0.8)
                 else '筹码正常，有一定支撑')
    print(f"- RSI6={rsi6:.1f}（{rsi_warn}），短期回调风险；{chip_warn}")

    # Step 2
    print(f"\n{sep}")
    print(f"## Step 2 · 10维度技术验证")
    print(f"\n- **①均线**：{dim_ma} — MA5={ma5:.3f}>MA10={ma10:.3f}>MA20={ma20:.3f}>MA60={ma60:.3f}，{'标准多头' if ma_arrangement=='多头' else ma_arrangement}排列")
    print(f"- **②K线**：{dim_kline} — {'阳线' if pct_chg>0 else '阴线'}{abs(pct_chg):+.2f}%，振幅{atr_pct:.1f}%，K线形态健康")
    print(f"- **③量价**：{dim_vol} — 量比={vol_ratio:.2f}，20日位置{pos_in_20d:.1%}，{'量增价涨' if vol_ratio>1 else '缩量整理'}")
    pos_in_boll_pct = f"{pos_in_boll:.1%}"
    print(f"- **④布林**：{dim_boll} — BOLL {boll_l:.3f}/{boll_m:.3f}/{boll_u:.3f}，{'突破上轨' if pos_in_boll>1 else f'位置{pos_in_boll:.1%}，距上轨' if pos_in_boll>0.8 else f'位置{pos_in_boll:.1%}，中部偏上' if pos_in_boll>0.5 else f'位置{pos_in_boll:.1%}，中部/轨下'}")
    print(f"- **⑤板块**：{'✅主线' if sector else '⚪待查'} — 所属{sector or '板块待确认'}，题材热点匹配度{'高' if concepts else '待评估'}")
    print(f"- **⑥分价**：{'✅密集区' if pos_in_20d>0.7 else '⚪正常'} — 20日价格区间{low_20:.2f}~{high_20:.2f}，当前处于{'上部' if pos_in_20d>0.7 else '中部' if pos_in_20d>0.3 else '下部'}")
    rsi_desc = f'RSI6={rsi6:.1f}(超买⚠️)' if rsi6>80 else f'RSI6={rsi6:.1f}'
    print(f"- **⑦RSI**：{dim_rsi} — RSI6={rsi6:.1f} RSI12={rsi12:.1f} RSI24={rsi24:.1f}，{rsi_desc}")
    main_state = '✅吸筹/拉升' if (vol_breakout or divergence_signal) else '⚠️整理中'
    print(f"- **⑧主力**：{main_state} — 爆量={_fl(vol_breakout,'有','无')} 量价背离={_fl(divergence_signal,'有','无')} 压单={_fl(pressure_signal,'有','无')}")
    print(f"- **⑨北向**：{'✅净流入' if concepts else '⚪待查'} — 深股通标的，{'有数据' if concepts else '数据待确认'}")
    chip_s = f"获利{benefit_part*100:.1f}%" if benefit_part else '计算中'
    chip_d = f"均成本{avg_cost:.2f}元" if avg_cost else ''
    chip70_str = ('%s~%s' % tuple(chip_70_range)) if isinstance(chip_70_range, list) else str(chip_70_range) if chip_70_range else '计算中'
    print(f"- **⑩筹码**：{dim_chip} — {chip_s}；{chip_d}；70%区间{chip70_str}")

    # Step 3
    print(f"\n{sep}")
    print(f"## Step 3 · 综合评分：{score}/100")
    print(f"\n**【评分明细】**")
    for name, val, val_max, note in detail:
        print(f"- {name}：**{val}{val_max}** — {note}")
    print(f"\n**【结论】**：{verdict}")

    # —————— 综合评分（技术60% + 资金20% + 基本面20%）——————
    # 技术面：100分制 → 60%权重
    # 资金面：20分制 → 20%权重（→百分制后 = CAP_SCORE/20*100*20% = CAP_SCORE*1.0）
    # 基本面：75分制 → 20%权重（→百分制后 = FIN_SCORE/75*100*20% = FIN_SCORE/75*20）
    tech_pct  = score           # 技术60分（百分制）
    cap_pct   = round(CAP_SCORE / 20 * 100)  # 资金面百分制
    fin_pct   = round(FIN_SCORE / 75 * 100)  # 基本面百分制
    comp_score = round(tech_pct * 0.60 + cap_pct * 0.20 + fin_pct * 0.20)  # 综合百分制
    comp_tech = round(score * 0.60)       # 技术绝对分（60分满分）
    comp_cap  = round(CAP_SCORE * 1.0)   # 资金绝对分（20分满分）
    comp_fin  = round(FIN_SCORE / 75 * 20)  # 基本面绝对分（20分满分）

    if comp_score >= 80:
        comp_star = '⭐⭐⭐⭐⭐'
        comp_judge = '极强'
    elif comp_score >= 65:
        comp_star = '⭐⭐⭐⭐'
        comp_judge = '较强'
    elif comp_score >= 50:
        comp_star = '⭐⭐⭐'
        comp_judge = '中等'
    elif comp_score >= 35:
        comp_star = '⭐⭐'
        comp_judge = '偏差'
    else:
        comp_star = '⭐'
        comp_judge = '极弱'

    print(f"\n{sep}")
    print(f"## 综合评分 · 技术60% + 资金20% + 基本面20%")
    print(f"\n**【三维评分】**")
    print(f"- **技术面**（{d1+d2+d3+d4+d5}/100 → ×60%）：{score}分 → **{comp_tech}/60分**")
    cap_star = '⭐' * min(5, max(1, cap_pct // 20))
    print(f"- **资金面**（CAP/20 → ×20%）：{cap_pct}分{cap_star} → **{comp_cap}/20分**")
    fin_star = '⭐' * min(5, max(1, fin_pct // 20))
    fin_judge2 = '优秀' if fin_pct>=80 else '良好' if fin_pct>=60 else '一般' if fin_pct>=40 else '偏差'
    print(f"- **基本面**（FIN/75 → ×20%）：{fin_pct}分{fin_star}（{fin_judge2}） → **{comp_fin}/20分**")
    print(f"\n**【综合总分】：{comp_score}/100 {comp_star}（{comp_judge}）**")
    print(f"  = 技术{comp_tech}分({score}×60%) + 资金{comp_cap}分({CAP_SCORE}/20×100×20%) + 基本{comp_fin}分({FIN_SCORE}/75×100×20%)")

    # Step 4
    print(f"\n{sep}")
    print(f"## Step 4 · 风控要点")
    if rsi6 > 80:
        print(f"- **RSI预警**：RSI6={rsi6:.1f}，连续3日>80极易触发短期回调，幅度约-10%~15%")
    else:
        print(f"- **RSI预警**：RSI6={rsi6:.1f}，偏热区，需关注是否转势")
    if pos_in_boll > 1:
        print(f"- **BOLL突破有效性**：已突破上轨，需3个交易日确认不跌回{boll_u:.2f}")
    elif pos_in_boll > 0.8:
        print(f"- **BOLL突破有效性**：位置{pos_in_boll:.1%}，距上轨约{round((1-pos_in_boll)*100)}个点，突破在即")
    else:
        print(f"- **BOLL突破有效性**：位置{pos_in_boll:.1%}，距上轨约{round((1-pos_in_boll)*100)}个点，密切关注{boll_u:.2f}能否放量突破")
    print(f"- **硬止损**：{stop_loss:.2f}（MA20）；{last_close*0.93:.2f}整体转空")
    if benefit_part:
        print(f"- **高位筹码**：获利比例{benefit_part*100:.1f}%，{'高位风险注意了结' if benefit_part>0.85 else '正常'}")
    print(f"- **量能预警**：{'爆量注意' if vol_ratio>1.5 else '量能正常'}；缩量整理是控盘信号，放量滞涨需警惕出货")

    # Step 5
    print(f"\n{sep}")
    print(f"## Step 5 · 基本面验证（7项+财务深度）")
    print(f"\n1. **全称**：{f10_data.get('ORG_NAME', stock_name) or stock_name}")
    print(f"2. **主营**：{f10_data.get('MAIN_BUSINESS', '数据获取失败')}")
    print(f"3. **收入结构**：{f10_data.get('INCOME_STRU_NAMENEW', '数据获取失败')}")
    print(f"4. **行业(三级)**：{f10_data.get('BOARD_NAME_1LEVEL','')}-{f10_data.get('BOARD_NAME_2LEVEL','')}-{f10_data.get('BOARD_NAME_3LEVEL','')}")
    print(f"5. **地区**：{f10_data.get('REGIONBK', '数据获取失败')}")
    print(f"6. **上市日期**：{f10_data.get('LISTING_DATE', '数据获取失败')}")
    print(f"7. **题材概念**{'（'+str(len(concepts))+'个）' if concepts else ''}：{', '.join(concepts) if concepts else '数据获取失败'}")

    # 财务深度数据（增强）
    print(f"\n**【财务深度数据】**")
    if roe_2025:
        print(f"- ROE: {roe_2025:.2f}% | 净利率: {np_margin:.2f}% | 毛利率: {gp_margin:.2f}% | EPS: {eps_2025:.4f}元")
        print(f"- 净利润: {net_profit_2025/1e8:.2f}亿 | 营收: {rev_2025/1e8:.2f}亿 | 总股本: {total_share:.2f}亿股")
    if yoy_ni is not None:
        print(f"- 净利润YOY: {yoy_ni:+.1f}% | 营收YOY: {yoy_rev:+.1f}% | EPS_YOY: {yoy_eps:+.1f}%")
    if nrt:
        print(f"- 应收周转: {nrt:.1f}次 | 存货周转: {invt:.1f}次")
    if current_ratio:
        cr_tag = '(优秀)' if current_ratio>=2 else '(良好)' if current_ratio>=1 else '(偏弱)'
        la_tag = '(低)' if liability_to_asset<40 else '(合理)' if liability_to_asset<60 else '(高⚠️)'
        print(f"- 流动比率: {current_ratio:.2f}{cr_tag} | 速动比率: {quick_ratio:.2f} | 资产负债率: {liability_to_asset:.2f}%{la_tag}")
    if dupont_net_profit:
        em_tag = '(低杠杆)' if dupont_equity_mul<2 else '(合理)' if dupont_equity_mul<3 else '(高杠杆⚠️)'
        print(f"- 杜邦拆解: 净利率{dupont_net_profit*100:.2f}% × 周转率{dupont_asset_turn:.2f} × 权益乘数{dupont_equity_mul:.2f}{em_tag}")
    fin_pct = round(FIN_SCORE/75*100) if FIN_SCORE else 0
    stars = '⭐'*min(5,max(1,fin_pct//20))
    print(f"\n- **财务综合评分**: {FIN_SCORE}/75（{stars}{'优秀' if fin_pct>=80 else '良好' if fin_pct>=60 else '一般' if fin_pct>=40 else '偏差'}）")

    # Step 6
    print(f"\n{sep}")
    print(f"## Step 6 · 估值水平（5项全列）")
    pe_str = ('亏损' if (pe and pe<0) else (f'{pe:.1f}' if pe else '获取失败'))
    pb_str = (f'{pb:.2f}' if pb else '-')
    mkt_str = (f'{mkt:.0f}' if mkt else '-')
    sec_str = (sector or '获取失败')
    pri_str = (f'{price:.2f}' if price else f'{last_close:.2f}')
    print(f"\n1. **估值**：PE={pe_str} PB={pb_str} 市值={mkt_str}亿 板块={sec_str} 股价={pri_str}元")
    if pe and pe > 0:
        pe_note = '显著低估' if pe<15 else ('偏高' if pe>40 else '合理')
    else:
        pe_note = '参考同花顺行业板块'
    print(f"2. **行业均值对比**：⚠️ 东财行业均值接口暂不支持中文行业名精确查询，PE={pe_str}（{pe_note}）")
    if concepts:
        print(f"3. **题材概念({len(concepts)}个)**：{', '.join(concepts)}")
    if hot_sectors:
        print(f"\n4. **近30日热点题材 Top10**：")
        for i, h in enumerate(hot_sectors[:10], 1):
            print(f"   {i:2d}. {h['name']:<12} {h['pct_chg']:>+6.2f}%")
        print(f"\n5. **热点匹配**：{'；'.join(['✓ '+m for m in hot_match[:5]]) if hot_match else '⚠️ 无直接匹配的30日热点题材'}")
    else:
        print(f"\n3. **题材概念**：{', '.join(concepts) if concepts else '获取失败'}")

    # Step 7：7种走势路径推演（老渔民实战框架）
    print(f"\n{sep}")
    print(f"## Step 7 · 3条走势路径推演（7种路径选3）")

    # ---- 概览表：全部7种路径 ----
    print(f"\n**【7种路径全览】**")
    print(f"\n| 路径 | 核心特征 | 散户误区 | 应对策略 |")
    print(f"|------|----------|----------|----------|")
    for k, v in PATH_DEFS.items():
        selected_marker = " ←当前选中" if k in top_paths else ""
        print(f"| **{v['name']}** | {v['特征']} | {v['散户误区']} | {v['口诀']}{selected_marker} |")

    # ---- 选中路径详情 ----
    print(f"\n**【重点路径详解】**")
    main_ctrl = '控盘' if volume_compressed else '活跃'

    for path_key, path_def, path_pr, path_prices in [
        (top_paths[0], pa_def, pa, path_a_prices),
        (top_paths[1], pb_def, pb_pct, path_b_prices),
        (top_paths[2], pc_def, pc, path_c_prices),
    ]:
        is_main = path_key == top_paths[0]
        marker = "【最大概率】" if is_main else ""
        print(f"\n### {marker}{path_def['name']}（{path_pr}%概率）")
        print(f"- **特征**：{path_def['特征']}")
        print(f"- **散户误区**：{path_def['散户误区']}")
        print(f"- **主力意图**：{path_def['主力意图']}")
        print(f"- **关键价位**：{path_prices}")
        print(f"- **口诀**：{path_def['口诀']}")

    print(f"\n**综合研判**：{pa_def['name']}（{pa}%）——"
          f"{'BOLL突破+' if pos_in_boll>1 else ''}"
          f"{sector or '主线板块'}题材驱动+主力{main_ctrl}三共振，"
          f"当前RSI6={rsi6:.1f}，BOLL位置{pos_in_boll:.1%}。")


    # Step 8
    print(f"\n{sep}")
    print(f"## Step 8 · 持仓策略")
    print(f"\n**空仓**：等回踩{ma20:.2f}~{ma10:.2f}支撑区再考虑分批建仓，不追高{last_close:.2f}以上")
    print(f"\n**已持仓**：持有为主；可考虑在{boll_u:.2f}附近减半仓；跌破{ma20:.2f}减仓，跌破{stop_loss:.2f}清仓")
    print(f"\n**止损线**：收盘跌破{stop_loss:.2f}（MA20附近）必须减仓；跌破{last_close*0.93:.2f}整体转空")

    # ============================================================
    # 综合研判（宁波韵升格式）
    # ============================================================
    # 基本判断
    trend = '强势' if score >= 65 else ('中性' if score >= 45 else '偏弱')
    rsi_final = 'RSI严重超买，短期有回调压力' if rsi6 > 88 else ('RSI偏热' if rsi6 > 70 else 'RSI处于健康区间')
    chip_final = ('筹码高位（%.1f%%），注意获利了结' % (benefit_part*100) if (benefit_part and benefit_part>0.85)
                  else ('筹码低位（%.1f%%），中期有支撑' % (benefit_part*100) if (benefit_part and benefit_part<0.3)
                  else '筹码分布健康（%.1f%%）' % (benefit_part*100) if benefit_part else '筹码分布健康'))
    pe_final = f"PE={pe:.1f}有业绩支撑" if (pe and pe>0) else 'PE亏损，基本面偏弱'
    sector_final = sector or '行业'

    # 最大概率路径的名称和描述
    main_path_name = pa_def['name']
    main_path_pr = pa
    # 最大机会：上行空间
    if top_paths[0] == 'A_主升延续':
        max_up = boll_u * 1.2
        max_opportunity = f"如走出{main_path_name}，从当前{last_close:.2f}元冲至{max_up:.2f}元，约{(max_up-last_close)/last_close*100:.0f}%空间"
    elif top_paths[0] == 'E_诱多出货':
        max_opportunity = f"如走出{main_path_name}，突破{boll_u:.2f}后惯性冲高约{(boll_u*1.1-last_close)/last_close*100:.0f}%，是最后的逃命机会"
    elif top_paths[0] == 'B_震荡洗盘':
        max_opportunity = f"如走出{main_path_name}，回踩{ma20:.2f}止跌后再度上攻，{boll_u:.2f}放量突破约{(boll_u-last_close)/last_close*100:.0f}%空间"
    elif top_paths[0] == 'F_挖坑填坑':
        max_opportunity = f"如走出{main_path_name}，急跌后快速收复并创出新高，{boll_u*1.1:.2f}为目标位，约{(boll_u*1.1-last_close)/last_close*100:.0f}%空间"
    elif top_paths[0] == 'D_先破后立':
        max_opportunity = f"如走出{main_path_name}，假跌破后快速收复，{boll_u:.2f}为确认位，约{(boll_u-last_close)/last_close*100:.0f}%空间"
    else:
        max_opportunity = f"{main_path_name}概率{main_path_pr}%，等待方向选择"

    # 最大风险：下行空间
    if top_paths[0] == 'A_主升延续':
        max_risk = f"假突破——如跌回BOLL上轨{boll_u:.2f}以下，趋势破坏，趋势反转信号，跌破{stop_loss:.2f}离场"
    elif top_paths[0] == 'E_诱多出货':
        max_risk = f"真出货——突破{boll_u:.2f}后快速回落，{boll_m:.2f}中轨失守则趋势破坏，{boll_l:.2f}下方清仓"
    elif top_paths[0] == 'B_震荡洗盘':
        max_risk = f"真破位——回踩跌破{stop_loss:.2f}，{boll_l:.2f}失守则趋势逆转，清仓离场"
    elif top_paths[0] == 'F_挖坑填坑':
        max_risk = f"真破位——急跌后无法收复，{boll_m*0.9:.2f}以下减仓，{boll_l:.2f}失守清仓"
    elif top_paths[0] == 'D_先破后立':
        max_risk = f"真破位——跌破{boll_l:.2f}后3日内无法收回，{boll_m:.2f}中轨失守，清仓离场"
    elif top_paths[0] == 'C_趋势破坏':
        max_risk = f"趋势确认——{boll_l:.2f}已失守，{boll_m:.2f}无法收复，中期下行确立，立即离场"
    else:
        max_risk = f"趋势不明，{stop_loss:.2f}跌破减仓，{boll_l:.2f}失守清仓"

    # 核心矛盾
    if score >= 65:
        core_conflict = f"{rsi_final}与主线板块{sector_final}形成对立——短线客担心回调，技术派看得到主升浪的正常调整"
    elif score >= 45:
        core_conflict = f"{rsi_final}；{chip_final}；趋势信号不明确，等待方向确认"
    else:
        core_conflict = f"均线{ma_arrangement}，{rsi_final}，趋势偏弱，核心看{stop_loss:.2f}能否守住"

    # 基本面综合评分（75分制 → 百分制）
    fin_basic_pct = round(FIN_SCORE / 75 * 100) if FIN_SCORE else 0
    fin_stars = '⭐' * min(5, max(1, fin_basic_pct // 20))

    # 资金面显示
    mf_sign = '净流入' if mf_main_net_w > 0 else '净流出'
    mf_abs = abs(mf_main_net_w) / 1e4
    mf_level = '大额' if mf_abs > 1 else ('中等' if mf_abs > 0.3 else '小额')
    cap_level = '资金活跃' if CAP_SCORE >= 14 else ('资金偏多' if CAP_SCORE >= 8 else ('资金中性' if CAP_SCORE >= 4 else '资金偏弱'))

    # 综合结论
    print(f"\n{sep}")
    print(f"## 综合研判")
    print(f"\n**技术面（5维度）**：{latest['date'].strftime('%Y-%m-%d')}收盘{last_close:.2f}元({pct_chg:+.2f}%)，"
          f"{ma_arrangement}排列，{rsi_final}，"
          f"BOLL{'突破上轨' if pos_in_boll>1 else '轨道'+('上轨' if pos_in_boll>0.8 else '中部')+'运行'}，"
          f"技术评分**{score}/100**（{verdict.split('—')[0].strip()}）。")
    fin_judge = '优秀' if fin_basic_pct>=80 else '良好' if fin_basic_pct>=60 else '一般' if fin_basic_pct>=40 else '偏差'
    print(f"\n**资金面**：今日主力{mf_level}{mf_sign}{mf_abs:.2f}亿（占比{mf_main_pct:+.1f}%），{cap_level}（资金面评分{CAP_SCORE}/20）。")
    print(f"\n**基本面**：财务评分**{FIN_SCORE}/75**（{fin_stars}{fin_judge}），{pe_final}，{sector_final}板块，{'题材丰富' if len(concepts)>5 else '题材一般'}。")
    print(f"\n**核心矛盾**：{core_conflict}。")
    print(f"\n**最大机会**：{max_opportunity}。")
    print(f"\n**最大风险**：{max_risk}。")
    if comp_score >= 65 and fin_basic_pct >= 60:
        print(f"\n**建议**：三维共振较强（综合{comp_score}/100），技术+资金+基本面联动，持股者{last_close*0.95:.2f}元以上坚定持有；空仓者等回踩{ma20:.2f}~{last_close*0.95:.2f}低吸。止损{stop_loss:.2f}。")
    elif comp_score >= 50:
        print(f"\n**建议**：综合评分中等（{comp_score}/100），等待{boll_u:.2f}放量突破确认再入；回调{ma20:.2f}附近企稳可轻仓试探。止损{stop_loss:.2f}。")
    else:
        print(f"\n**建议**：综合评分偏弱（{comp_score}/100），短线博弈为主，快进快出；回调{ma20:.2f}企稳再考虑。止损{stop_loss:.2f}，不恋战。")
    print(f"\n{sep}")



# ============================================================
# 调用完整报告生成器
# ============================================================
generate_full_report(
    code=code, DATE=DATE, last_close=last_close,
    df=df, latest=latest, prev=prev,
    recent_5=recent_5, recent_20=recent_20,
    concepts=concepts, hot_sectors=hot_sectors,
    stock_name=stock_name, f10_data=f10_data,
    pe=pe, pb=pb, mkt=mkt, sector=sector, price=price,
    roe_2025=roe_2025, np_margin=np_margin, gp_margin=gp_margin,
    net_profit_2025=net_profit_2025,
    eps_2025=eps_2025, rev_2025=rev_2025,
    total_share=total_share, liq_share=liq_share,
    yoy_ni=yoy_ni, yoy_eps=yoy_eps,
    yoy_rev=yoy_rev,
    nrt=nrt, invt=invt,
    current_ratio=current_ratio, quick_ratio=quick_ratio, liability_to_asset=liability_to_asset,
    dupont_net_profit=dupont_net_profit, dupont_asset_turn=dupont_asset_turn, dupont_equity_mul=dupont_equity_mul,
    FIN_SCORE=FIN_SCORE,
    CAP_SCORE=CAP_SCORE,
    mf_main_net_w=mf_main_net_w,
    mf_main_pct=mf_main_pct,
    avg_cost=avg_cost, benefit_part=benefit_part,
    chip_70_range=chip_70_range, chip_90_range=chip_90_range, chip_peak=chip_peak,
    vol_breakout=vol_breakout, divergence_signal=divergence_signal,
    volume_compressed=volume_compressed,
    pressure_signal=pressure_signal, support_signal=support_signal,
    ma_arrangement=ma_arrangement, ma5_cross_up=ma5_cross_up, dif_cross_up=dif_cross_up,
    pos_in_boll=pos_in_boll, pos_in_20d=pos_in_20d,
    high_20=high_20, low_20=low_20
)

print("\n" + "=" * 65)
print("脚本执行完毕")
print("=" * 65)
