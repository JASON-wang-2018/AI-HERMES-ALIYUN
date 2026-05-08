import pandas as pd
import baostock as bs
import numpy as np
import subprocess
import json
import urllib.parse
import sys
sys.path.insert(0, '/home/admin/stock_knowledge/scripts')

code = '002491'  # 深市

# ===== Step 1: 近15日详细K线 =====
print("=" * 60)
print("【Step 1 定性定位 - 近15日详细数据】")
print("=" * 60)

bs.login()
bs_code = f'sz.{code}'

rs2 = bs.query_history_k_data_plus(bs_code,
    'date,open,high,low,close,volume,amount,pctChg',
    start_date='2026-04-15', end_date='2026-05-06',
    frequency='d', adjustflag='2')
detail = []
while rs2.next():
    detail.append(rs2.get_row_data())
df_det = pd.DataFrame(detail, columns=rs2.fields)
for col in ['open','high','low','close','volume','amount','pctChg']:
    df_det[col] = pd.to_numeric(df_det[col], errors='coerce')
df_det['date'] = pd.to_datetime(df_det['date'])
df_det = df_det.sort_values('date').reset_index(drop=True)

print(f"\n日期        开    高    低    收   涨跌%   量(万)  成交(亿)")
print("-" * 65)
for _, r in df_det.iterrows():
    print(f"{r['date'].strftime('%Y-%m-%d')}  {r['open']:>6.2f} {r['high']:>6.2f} {r['low']:>6.2f} {r['close']:>6.2f} {r['pctChg']:>+6.2f}% {r['volume']/1e4:>8.0f}万 {r['amount']/1e8:>6.2f}亿")

bs.logout()

# ===== 完整一年数据 =====
bs.login()
rs = bs.query_history_k_data_plus(bs_code,
    'date,open,high,low,close,volume,amount,pctChg',
    start_date='2025-05-01', end_date='2026-05-06',
    frequency='d', adjustflag='2')
data = []
while rs.next():
    data.append(rs.get_row_data())
df = pd.DataFrame(data, columns=rs.fields)
for col in ['open','high','low','close','volume','amount','pctChg']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)
bs.logout()

print(f"\n总数据: {len(df)} 条, 日期范围: {df['date'].min()} ~ {df['date'].max()}")

# ===== 技术指标 =====
for ma in [5,10,20,60]:
    df['ma'+str(ma)] = df['close'].rolling(ma, min_periods=1).mean()

df['dif'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
df['macd'] = (df['dif'] - df['dea']) * 2

l9 = df['low'].rolling(9, min_periods=1).min()
h9 = df['high'].rolling(9, min_periods=1).max()
rsv = (df['close'] - l9) / (h9 - l9 + 0.0001) * 100
df['k'] = rsv.ewm(com=2, adjust=False).mean()
df['d'] = df['k'].ewm(com=2, adjust=False).mean()
df['j'] = 3*df['k'] - 2*df['d']

for p in [6,12,24]:
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(p, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(p, min_periods=1).mean()
    df['rsi'+str(p)] = 100 - (100 / (1 + gain/(loss+0.0001)))

ma20_s = df['close'].rolling(20, min_periods=1).mean()
std20 = df['close'].rolling(20, min_periods=1).std()
df['boll_u'] = ma20_s + 2*std20
df['boll_m'] = ma20_s
df['boll_l'] = ma20_s - 2*std20

df['vol_ma5'] = df['volume'].rolling(5, min_periods=1).mean()
df['vol_ma20'] = df['volume'].rolling(20, min_periods=1).mean()
df['vol_ratio'] = df['volume'] / df['vol_ma20']

hl = df['high'] - df['low']
hc = abs(df['high'] - df['close'].shift())
lc = abs(df['low'] - df['close'].shift())
tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
df['atr'] = tr.rolling(14, min_periods=1).mean()
df['atr_pct'] = df['atr'] / df['close'] * 100

latest = df.iloc[-1]
prev = df.iloc[-2]
recent_5 = df.tail(5)
recent_20 = df.tail(20)

# 主力行为
vol_prev_avg = df.iloc[-25:-5]['volume'].mean() if len(df) >= 25 else df['volume'].mean()
price_trend_5 = recent_5['close'].iloc[-1] - recent_5['close'].iloc[0]
vol_trend_5 = recent_5['volume'].iloc[-1] - recent_5['volume'].iloc[0]
divergence_signal = (price_trend_5 > 0 and vol_trend_5 < 0) or (price_trend_5 < 0 and vol_trend_5 > 0)
volume_compressed = recent_5['volume'].mean() < vol_prev_avg * 0.6
vol_breakout = latest['vol_ratio'] > 1.5 and latest['pctChg'] > 2.0
high_upper = latest['high'] - max(latest['open'], latest['close'])
low_lower = min(latest['open'], latest['close']) - latest['low']
body = abs(latest['close'] - latest['open'])
pressure_signal = body > 0.01 and high_upper > body * 1.5
support_signal = body > 0.01 and low_lower > body * 1.5
high_20 = recent_20['high'].max()
low_20 = recent_20['low'].min()
pos_in_boll = (latest['close'] - latest['boll_l']) / (latest['boll_u'] - latest['boll_l'] + 0.001)
pos_in_20d = (latest['close'] - low_20) / (high_20 - low_20 + 0.001)
ma_arrangement = '多头' if latest['ma5'] > latest['ma10'] > latest['ma20'] else '空头' if latest['ma5'] < latest['ma10'] < latest['ma20'] else '缠绕'
ma5_cross_up = (latest['ma5'] > latest['ma10']) and (prev['ma5'] <= prev['ma10'])
dif_cross_up = (latest['dif'] > latest['dea']) and (prev['dif'] <= prev['dea'])

print("\n" + "=" * 60)
print("【技术指标汇总】")
print("=" * 60)
print(f"""
【收盘】{latest['date'].strftime('%Y-%m-%d')}  {latest['close']:.2f}元  涨跌:{latest['pctChg']:+.2f}%  ATR%:{latest['atr_pct']:.2f}%

【均线】MA5={latest['ma5']:.3f}  MA10={latest['ma10']:.3f}  MA20={latest['ma20']:.3f}  MA60={latest['ma60']:.3f}
      均线排列: {ma_arrangement}  5日线上穿10日线: {'是' if ma5_cross_up else '否'}

【MACD】 DIF={latest['dif']:.4f}  DEA={latest['dea']:.4f}  MACD={latest['macd']:.4f} ({'红柱' if latest['macd']>0 else '绿柱'})  金叉:{'是' if dif_cross_up else '否'}

【KDJ】 K={latest['k']:.2f}  D={latest['d']:.2f}  J={latest['j']:.2f}  ({'超买' if latest['k']>80 else '超卖' if latest['k']<20 else '正常'})

【RSI】 RSI6={latest['rsi6']:.1f}  RSI12={latest['rsi12']:.1f}  RSI24={latest['rsi24']:.1f}

【BOLL】 上轨={latest['boll_u']:.3f}  中轨={latest['boll_m']:.3f}  下轨={latest['boll_l']:.3f}  位置:{pos_in_boll:.1%}

【量价】 量比={latest['vol_ratio']:.2f}  20日位置:{pos_in_20d:.1%}
         5日涨跌:{price_trend_5:+.2f}元  5日量变化:{vol_trend_5/+1e8:.2f}亿

【主力行为】
  - 量价背离: {'有' if divergence_signal else '无'}
  - 缩量整理: {'是' if volume_compressed else '否'}
  - 爆量拉升: {'是' if vol_breakout else '否'}
  - 压盘痕迹: {'有' if pressure_signal else '无'}
  - 托单痕迹: {'有' if support_signal else '无'}
  - 上影线:{high_upper:.2f}  下影线:{low_lower:.2f}  实体:{body:.2f}
""")

# ===== 东财数据 =====
print("=" * 60)
print("【估值与基本面】")
print("=" * 60)

def curl_json(url):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                       capture_output=True, text=True, timeout=20)
    try:
        return json.loads(r.stdout)
    except:
        return {}

DATE = '2026-05-06'

# 估值
FILTER_V = urllib.parse.quote(f"(TRADE_DATE='{DATE}')(SECURITY_CODE={code})")
url_val = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_VALUEANALYSIS_DET"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
    f"&pageNumber=1&pageSize=1&filter={FILTER_V}&source=WEB&client=WEB"
)
r_val = curl_json(url_val)
pe_val, pb_val, mkt_val, sector_val, price_val = 0, 0, 0, '', 0
if r_val.get('result') and r_val['result'].get('data'):
    vc = r_val['result']['data'][0]
    pe_val = vc.get('PE_TTM', 0)
    pb_val = vc.get('PB_MRQ', 0)
    mkt_val = vc.get('TOTAL_MARKET_CAP', 0) / 1e8
    sector_val = vc.get('BOARD_NAME', '')
    price_val = vc.get('CLOSE_PRICE', 0)
    print(f"估值: PE={pe_val:.1f}  PB={pb_val:.2f}  市值={mkt_val:.0f}亿  板块={sector_val}  股价={price_val:.2f}")

# 基本面
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
if r_f10.get('result') and r_f10['result'].get('data'):
    co = r_f10['result']['data'][0]
    print(f"\n简称: {co['SECURITY_NAME_ABBR']}")
    print(f"全称: {co['ORG_NAME']}")
    print(f"主营: {co['MAIN_BUSINESS']}")
    print(f"收入结构: {co['INCOME_STRU_NAMENEW']}")
    print(f"行业(三级): {co['BOARD_NAME_1LEVEL']}-{co['BOARD_NAME_2LEVEL']}-{co['BOARD_NAME_3LEVEL']}")
    print(f"地区: {co['REGIONBK']}  上市日期: {co['LISTING_DATE']}")

# 题材概念
secid = f"0.{code}"
url_concept = (
    f"https://push2delay.eastmoney.com/api/qt/stock/get"
    f"?secid={secid}&fields=f58,f57,f129"
    f"&ut=fa5fd1943c7b386f172d6893dbfba10b"
)
r_con = curl_json(url_concept)
concepts = []
if r_con.get('data') and r_con['data'].get('f129'):
    concepts = [c.strip() for c in r_con['data']['f129'].split(',') if c.strip()]
    print(f"\n题材概念({len(concepts)}个): {concepts}")

# 近30日热点题材
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
            'name': item.get('f14',''),
            'pct_chg': item.get('f3', 0),
            'main_force': item.get('f62', 0)
        })
    print(f"\n近30日热点题材 Top15:")
    for i, h in enumerate(hot_sectors[:15], 1):
        print(f"  {i:2d}. {h['name']:<12} {h['pct_chg']:>+6.2f}%")

print(f"\n⭐ 题材热点匹配:")
matched = []
for c in concepts:
    for h in hot_sectors[:30]:
        if c in h['name'] or h['name'] in c:
            matched.append({'concept': c, 'hot': h['name'], 'pct': h['pct_chg']})
            break
if matched:
    for m in matched:
        print(f"  ✓ {m['concept']} → {m['hot']} {m['pct']:+.2f}%")
else:
    print(f"  ⚠️ 无直接匹配的30日热点题材")

# 行业对比
if sector_val:
    FILTER_IND = urllib.parse.quote(f"(TRADE_DATE='{DATE}')(BOARD_NAME='{sector_val}')")
    url_ind = (
        "https://datacenter.eastmoney.com/api/data/v1/get"
        "?reportName=RPT_VALUEINDUSTRY_DET"
        "&columns=BOARD_NAME,PE_TTM,PB_MRQ,NUM,LOSS_COUNT"
        f"&pageNumber=1&pageSize=5&filter={FILTER_IND}&source=WEB&client=WEB"
    )
    r_ind = curl_json(url_ind)
    if r_ind.get('result') and r_ind['result'].get('data'):
        print(f"\n行业对比:")
        for ind in r_ind['result']['data']:
            print(f"  {ind['BOARD_NAME']} PE均值={ind['PE_TTM']:.1f}  PB={ind['PB_MRQ']:.2f}  个股数={ind['NUM']}")

# ===== 筹码分布 =====
print("\n" + "=" * 60)
print("【筹码分布 CYC成本】")
print("=" * 60)

bs.login()
rs_chip = bs.query_history_k_data_plus(bs_code,
    'date,open,high,low,close,volume,amount,pctChg,turn',
    start_date='2025-08-01', end_date='2026-05-06',
    frequency='d', adjustflag='2')
chip_data = []
while rs_chip.next():
    chip_data.append(rs_chip.get_row_data())
df_chip = pd.DataFrame(chip_data, columns=rs_chip.fields)
for col in ['open','high','low','close','volume','turn']:
    df_chip[col] = pd.to_numeric(df_chip[col], errors='coerce')
df_chip = df_chip.rename(columns={'turn': 'turnover'})
df_chip['date'] = pd.to_datetime(df_chip['date'])
df_chip = df_chip.sort_values('date').reset_index(drop=True)
bs.logout()

from chip_distribution import calc_chip_distribution, chip_analysis_text
chip = calc_chip_distribution(df_chip, accuracy_factor=150, trading_days=210)
print(chip_analysis_text(chip, code, latest['close']))

df.to_csv('/tmp/002491_tech.csv', index=False)
df_det.to_csv('/tmp/002491_detail.csv', index=False)
print("\n数据已保存!")
