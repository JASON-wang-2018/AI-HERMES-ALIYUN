#!/usr/bin/env python3
"""
回测 Jason 优化公式（通达信源码复现）
"""
import baostock as bs, pandas as pd, numpy as np
from datetime import datetime, timedelta
import random

def curl_json(url, timeout=12):
    import subprocess, json
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                      capture_output=True, text=True, timeout=timeout)
    try: return json.loads(r.stdout)
    except: return {}

# 获取全市场代码
print("获取全市场股票列表...")
all_codes = []
for page in range(1, 30):
    url = (f"https://datacenter.eastmoney.com/api/data/v1/get"
           f"?reportName=RPT_F10_ORG_BASICINFO"
           f"&columns=SECURITY_CODE,SECURITY_NAME_ABBR"
           f"&pageNumber={page}&pageSize=200&sortColumns=SECURITY_CODE&sortTypes=1"
           f"&source=WEB&client=WEB")
    r = curl_json(url)
    if r.get('result') and r['result'].get('data'):
        for item in r['result']['data']:
            code = str(item['SECURITY_CODE'])
            if (code.startswith('6') or code.startswith('0') or code.startswith('3')) and len(code) == 6:
                all_codes.append((code, item['SECURITY_NAME_ABBR']))
    else: break
print(f"全市场: {len(all_codes)} 只")

# 采样200只
random.seed(2026)
sample = random.sample(all_codes, min(200, len(all_codes)))
print(f"采样: {len(sample)} 只")

# 历史回测
print("\n历史回测（240日窗口）...")
bs.login()
today = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=600)).strftime('%Y-%m-%d')

信号样本 = []
processed = 0

for code, name in sample:
    processed += 1
    if processed % 50 == 0: print(f"  进度: {processed}/{len(sample)}...")

    prefix = 'sh' if code.startswith('6') else 'sz'
    try:
        rs = bs.query_history_k_data_plus(
            f'{prefix}.{code}',
            'date,open,high,low,close,volume,amount',
            start_date=start_date, end_date=today,
            frequency='d', adjustflag='2')
        data = []
        while rs.next(): data.append(rs.get_row_data())
        if len(data) < 280: continue

        df = pd.DataFrame(data, columns=rs.fields)
        for col in ['open','high','low','close','volume','amount']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        # 计算各项指标
        df['MA120'] = df['close'].rolling(120).mean()
        df['MA5']   = df['close'].rolling(5).mean()
        df['MA10']  = df['close'].rolling(10).mean()
        df['MA20']  = df['close'].rolling(20).mean()
        df['MA5V']  = df['volume'].rolling(5).mean()
        df['MA60V'] = df['volume'].rolling(60).mean()
        df['HH240'] = df['high'].rolling(240).max()
        df['LL240'] = df['low'].rolling(240).min()
        df['VolRange240'] = (df['HH240'] - df['LL240']) / df['LL240'] * 100
        df['PricePos'] = (df['close'] - df['LL240']) / (df['HH240'] - df['LL240']) * 100
        df['VolRatio'] = df['MA5V'] / df['MA60V']

        # 遍历每个信号日（从240日开始）
        for i in range(260, len(df) - 60):
            c = df.iloc[i]
            c1 = df.iloc[i-1]

            # === 条件1: 市值亿（取最新一期近似：收盘*总股本）===
            # FINANCE(40)=总市值，单位元，用当日收盘*总股本估算
            # 此处用 None 跳过，后面单独补市值过滤

            # 条件2: C<=30 AND C>MA(C,120)
            if not (c['close'] <= 30 and c['close'] > c['MA120']): continue

            # 条件3: 15% <= 240日振幅 <= 50%
            vr = c['VolRange240']
            if not (15 <= vr <= 50): continue

            # 条件4: 25 <= 价格位置 <= 55
            pp = c['PricePos']
            if not (25 <= pp <= 55): continue

            # 条件5: 量比 <= 0.8 ← 已移除（方案B）
            # 趋势确认: MA5>MA10 AND MA10>MA20 AND C>MA5 AND C>MA20
            if not (c['MA5'] > c['MA10'] > c['MA20'] and c['close'] > c['MA5'] and c['close'] > c['MA20']): continue

            # 放量启动: V>REF(V,1)*1.5 AND V>MA(V,5) AND C>REF(C,1)
            if not (c['volume'] > c1['volume'] * 1.5 and c['volume'] > c['MA5V'] and c['close'] > c1['close']): continue

            # 计算未来30日收益
            future = df.iloc[i+1:i+31]['close']
            if len(future) < 20: continue
            cur_close = c['close']
            ret30_avg = (future.mean() / cur_close - 1) * 100
            ret30_max = (future.max() / cur_close - 1) * 100
            ret30_min = (future.min() / cur_close - 1) * 100

            信号样本.append({
                'code': code, 'name': name,
                'date': str(c['date'])[:10],
                'price': round(cur_close, 2),
                'vol_range': round(vr, 1),
                'price_pos': round(pp, 1),
                'vol_ratio': round(c['VolRatio'], 2),
                'ret30_avg': ret30_avg,
                'ret30_max': ret30_max,
                'ret30_min': ret30_min,
            })
    except Exception as e:
        continue

bs.logout()
df_sig = pd.DataFrame(信号样本)
print(f"\n总信号: {len(df_sig)} 个")

# 市值过滤
print("\n采集市值数据...")
import urllib.parse
DATE = '2026-05-08'
mkt_cache = {}
for code, _ in sample:
    FILTER_V = f"(TRADE_DATE='{DATE}')(SECURITY_CODE={code})"
    url_val = (f"https://datacenter.eastmoney.com/api/data/v1/get"
               f"?reportName=RPT_VALUEANALYSIS_DET"
               f"&columns=SECURITY_CODE,TOTAL_MARKET_CAP"
               f"&pageNumber=1&pageSize=1"
               f"&filter={urllib.parse.quote(FILTER_V)}&source=WEB&client=WEB")
    rv = curl_json(url_val)
    if rv.get('result') and rv['result'].get('data'):
        mkt_cache[code] = rv['result']['data'][0].get('TOTAL_MARKET_CAP', 0) / 1e8

df_sig['mkt_cap'] = df_sig['code'].map(mkt_cache)
df_with_mkt = df_sig[df_sig['code'].isin(mkt_cache)].copy()
df_mkt_ok = df_with_mkt[(df_with_mkt['mkt_cap'] >= 10) & (df_with_mkt['mkt_cap'] <= 300)]

# 统计函数
def calc_stats(df, label):
    if len(df) == 0:
        print(f"\n{label}: 无样本"); return
    print(f"\n{'='*58}")
    print(f"{label}")
    print(f"{'='*58}")
    print(f"总信号: {len(df)} 个")
    print(f"30日平均涨幅: {df['ret30_avg'].mean():+.2f}%")
    print(f"30日中位数涨幅: {df['ret30_avg'].median():+.2f}%")
    print(f"30日最高涨幅均值: {df['ret30_max'].mean():+.2f}%")
    print(f"30日最低涨幅均值: {df['ret30_min'].mean():+.2f}%")
    print(f"最大亏损: {df['ret30_min'].min():+.2f}%")
    print(f"\n--- 盈利概率（30日均幅 > X%）---")
    for t in [0, 3, 5, 8, 10, 15, 20]:
        cnt = (df['ret30_avg'] > t).sum()
        print(f"   >{t:>3}%: {cnt:>5}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"\n--- 最高涨幅概率（30日最高 > X%）---")
    for t in [0, 5, 10, 20, 30]:
        cnt = (df['ret30_max'] > t).sum()
        print(f"   >{t:>3}%: {cnt:>5}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"\n--- 亏损概率（30日均幅 < X%）---")
    for t in [-5, -10, -15, -20]:
        cnt = (df['ret30_avg'] < t).sum()
        print(f"   <{t:>5}%: {cnt:>5}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"\n--- 信号分布 ---")
    for lo, hi, lbl in [(0,5,'0-5元'),(5,10,'5-10元'),(10,20,'10-20元'),(20,30,'20-30元')]:
        sub = df[(df['price']>=lo)&(df['price']<hi)]
        if len(sub)>0:
            avg = sub['ret30_avg'].mean()
            win5 = (sub['ret30_avg']>5).sum()
            print(f"  {lbl}: {len(sub):>4}个  均幅{avg:>+6.1f}%  >5%概率{win5/len(sub)*100:.0f}%")

calc_stats(df_with_mkt, "优化后公式（技术条件全部满足，暂缺市值过滤）")
calc_stats(df_mkt_ok, "优化后公式（10亿≤市值≤300亿）")

# 各条件单独贡献
print(f"\n{'='*58}")
print("各条件单独贡献（样本内）")
# 各条件单独贡献（样本量太少，跳过）
# ...

# 当前标的
print(f"\n{'='*58}")
print("当前符合条件标的（2026-05-11）")
print(f"{'='*58}")
bs.login()
当前 = []
for code, name in sample:
    prefix = 'sh' if code.startswith('6') else 'sz'
    try:
        rs = bs.query_history_k_data_plus(
            f'{prefix}.{code}','date,open,high,low,close,volume',
            start_date=(datetime.now()-timedelta(days=300)).strftime('%Y-%m-%d'),
            end_date=today, frequency='d', adjustflag='2')
        data = []
        while rs.next(): data.append(rs.get_row_data())
        if len(data) < 280: continue
        df = pd.DataFrame(data, columns=rs.fields)
        for col in ['open','high','low','close','volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.sort_values('date').reset_index(drop=True)

        df['MA120'] = df['close'].rolling(120).mean()
        df['MA5']   = df['close'].rolling(5).mean()
        df['MA10']  = df['close'].rolling(10).mean()
        df['MA20']  = df['close'].rolling(20).mean()
        df['MA5V']  = df['volume'].rolling(5).mean()
        df['MA60V'] = df['volume'].rolling(60).mean()
        df['HH240'] = df['high'].rolling(240).max()
        df['LL240'] = df['low'].rolling(240).min()
        df['VolRange240'] = (df['HH240'] - df['LL240']) / df['LL240'] * 100
        df['PricePos'] = (df['close'] - df['LL240']) / (df['HH240'] - df['LL240']) * 100
        df['VolRatio'] = df['MA5V'] / df['MA60V']

        c = df.iloc[-1]
        c1 = df.iloc[-2]
        if all([
            c['close'] <= 30 and c['close'] > c['MA120'],
            15 <= c['VolRange240'] <= 50,
            25 <= c['PricePos'] <= 55,
            c['VolRatio'] <= 0.8,
            c['MA5'] > c['MA10'] > c['MA20'],
            c['close'] > c['MA5'], c['close'] > c['MA20'],
            c['volume'] > c1['volume'] * 1.5,
            c['volume'] > c['MA5V'],
            c['close'] > c1['close'],
        ]):
            mkt = mkt_cache.get(code, 0)
            if 10 <= mkt <= 300:
                当前.append({'code':code,'name':name,'price':round(c['close'],2),
                             'vr':round(c['VolRange240'],1),'pp':round(c['PricePos'],1),
                             'vr_ratio':round(c['VolRatio'],2),'mkt':round(mkt,0)})
    except: continue
bs.logout()

if 当前:
    df_cur = pd.DataFrame(当前).sort_values('vr')
    print(f"\n当前符合: {len(df_cur)} 只")
    for _, r in df_cur.iterrows():
        print(f"  {r['code']} {r['name']:<8} 价:{r['price']:.2f} 振幅:{r['vr']:.0f}% 价位置:{r['pp']:.0f}% 量比:{r['vr_ratio']:.2f} 市值:{r['mkt']:.0f}亿")
else:
    print("\n采样200只中无当前完全符合条件的标的")
    print("（注：量比≤0.8+放量启动组合条件较严格，属低频信号）")
