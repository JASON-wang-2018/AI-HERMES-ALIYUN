#!/usr/bin/env python3
"""
通达信低波动区间选股指标 + 回测验证 V2
"""

import subprocess, json, pandas as pd, numpy as np, baostock as bs, urllib.parse
from datetime import datetime, timedelta

def curl_json(url, timeout=12):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                      capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# ═══ 1. 获取全市场股票列表 ═══
print("获取全市场股票列表...")
all_codes = []
for page in range(1, 30):
    url = (
        "https://datacenter.eastmoney.com/api/data/v1/get"
        "?reportName=RPT_F10_ORG_BASICINFO"
        "&columns=SECURITY_CODE,SECURITY_NAME_ABBR"
        "&pageNumber={}&pageSize=200&sortColumns=SECURITY_CODE&sortTypes=1"
        "&source=WEB&client=WEB".format(page)
    )
    r = curl_json(url)
    if r.get('result') and r['result'].get('data') and len(r['result']['data']) > 0:
        for item in r['result']['data']:
            code = str(item['SECURITY_CODE'])
            if (code.startswith('6') or code.startswith('0') or code.startswith('3')) and len(code) == 6:
                all_codes.append((code, item['SECURITY_NAME_ABBR']))
    else:
        break
print(f"全市场A股: {len(all_codes)} 只")

# ═══ 2. 纯技术指标历史回测（跳过市值）═══
print("\n正在进行纯技术指标历史回测...")
bs.login()

today_str = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=450)).strftime('%Y-%m-%d')

信号样本_优化前 = []
processed = 0

for code, name in all_codes:
    processed += 1
    if processed % 500 == 0:
        print(f"  进度: {processed}/{len(all_codes)}...")

    prefix = 'sh' if code.startswith('6') else 'sz'
    try:
        rs = bs.query_history_k_data_plus(
            f'{prefix}.{code}',
            'date,open,high,low,close,volume',
            start_date=start_date, end_date=today_str,
            frequency='d', adjustflag='2'
        )
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        if len(data) < 200:
            continue

        df = pd.DataFrame(data, columns=rs.fields)
        for col in ['open','high','low','close','volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        for i in range(200, len(df) - 60):
            window180 = df.iloc[i-180:i]
            cur_close = df.iloc[i]['close']
            cur_date = df.iloc[i]['date']

            hh180 = window180['high'].max()
            ll180 = window180['low'].min()
            ratio = hh180 / ll180 if ll180 > 0 else 999

            if ratio >= 1.5:
                continue
            if cur_close > 39 or cur_close < 1:
                continue

            future_prices = df.iloc[i+1:i+31]['close']
            if len(future_prices) < 20:
                continue
            future_avg = future_prices.mean()
            future_max = future_prices.max()
            ret_30d = (future_avg / cur_close - 1) * 100
            ret_30d_max = (future_max / cur_close - 1) * 100

            信号样本_优化前.append({
                'code': code, 'name': name,
                'date': str(cur_date)[:10],
                'price': cur_close,
                'ratio': ratio,
                'ret_30d': ret_30d,
                'ret_30d_max': ret_30d_max,
            })
    except:
        continue

bs.logout()

df_before = pd.DataFrame(信号样本_优化前)

# ═══ 3. 市值数据：仅对当前候选股获取 ═══
# 先用东财批量接口拉全市场（粗筛，避免逐只查）
print("\n采集全市场市值数据...")
DATE = '2026-05-08'
fundamental_cache = {}
for i in range(0, len(all_codes), 50):
    batch = all_codes[i:i+50]
    codes_str = '+'.join([f"(SECURITY_CODE={c})" for c,_ in batch])
    FILTER = urllib.parse.quote(codes_str)
    url_val = (
        "https://datacenter.eastmoney.com/api/data/v1/get"
        "?reportName=RPT_VALUEANALYSIS_DET"
        "&columns=SECURITY_CODE,TOTAL_MARKET_CAP"
        "&pageNumber=1&pageSize=100"
        f"&filter=(TRADE_DATE='{DATE}')({codes_str})"
        "&source=WEB&client=WEB"
    )
    rv = curl_json(url_val)
    if rv.get('result') and rv['result'].get('data'):
        for v in rv['result']['data']:
            code = str(v['SECURITY_CODE'])
            fundamental_cache[code] = v.get('TOTAL_MARKET_CAP', 0) / 1e8

print(f"获取市值数据: {len(fundamental_cache)} 只")

# ═══ 4. 成功率统计（优化前）═══
def calc_stats(df, label):
    if len(df) == 0:
        print(f"\n{label}: 无样本")
        return
    print(f"\n{'='*55}")
    print(f"{label}")
    print(f"{'='*55}")
    print(f"总信号样本: {len(df)} 个")
    print(f"平均30日涨幅: {df['ret_30d'].mean():+.2f}%")
    print(f"中位数30日涨幅: {df['ret_30d'].median():+.2f}%")
    print(f"30日最高涨幅均值: {df['ret_30d_max'].mean():+.2f}%")
    print(f"\n--- 盈利概率（30日平均涨幅 > X%）---")
    print(f"  {'阈值':>6}  {'数量':>6}  {'成功率':>8}")
    for t in [0, 5, 10, 15, 20]:
        cnt = (df['ret_30d'] > t).sum()
        print(f"   >{t:>3}%  {cnt:>6}    {cnt/len(df)*100:>6.1f}%")
    print(f"\n--- 最高涨幅概率（30日最高 > X%）---")
    print(f"  {'阈值':>6}  {'数量':>6}  {'成功率':>8}")
    for t in [0, 5, 10, 20, 30]:
        cnt = (df['ret_30d_max'] > t).sum()
        print(f"   >{t:>3}%  {cnt:>6}    {cnt/len(df)*100:>6.1f}%")
    print(f"\n--- 亏损概率（30日平均涨幅 < X%）---")
    for t in [-5, -10, -20]:
        cnt = (df['ret_30d'] < t).sum()
        print(f"   <{t:>5}%  {cnt:>6}    {cnt/len(df)*100:>6.1f}%")
    print(f"\n--- 股价区间分布 ---")
    for lo, hi, label_r in [(0,5,'<5元'),(5,10,'5-10元'),(10,20,'10-20元'),(20,39,'20-39元')]:
        sub = df[(df['price']>=lo)&(df['price']<hi)]
        if len(sub) > 0:
            win10 = (sub['ret_30d']>10).sum()
            avg = sub['ret_30d'].mean()
            print(f"  {label_r}: {len(sub):>4}样本 10%概率{win10/len(sub)*100:>5.1f}% 均幅{avg:>+6.1f}%")

calc_stats(df_before, "优化前（技术条件：180日区间<50% + 股价<=39元）")

# 优化后（有市值数据的子集）
df_with_mkt = df_before[df_before['code'].isin(fundamental_cache.keys())].copy()
df_with_mkt['mkt_cap'] = df_with_mkt['code'].map(fundamental_cache)
df_after = df_with_mkt[df_with_mkt['mkt_cap'] <= 300]
calc_stats(df_after, "优化后（+ 总市值<=300亿，仅有市值数据的子集）")

# ═══ 5. 当前符合条件标的 ═══
print(f"\n{'='*55}")
print(f"当前符合条件标的（2026-05-11）")
print(f"{'='*55}")

bs.login()
today_str2 = datetime.now().strftime('%Y-%m-%d')
start2 = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')

当前符合 = []
for code, name in all_codes:
    try:
        prefix = 'sh' if code.startswith('6') else 'sz'
        rs = bs.query_history_k_data_plus(
            f'{prefix}.{code}',
            'date,open,high,low,close,volume',
            start_date=start2, end_date=today_str2,
            frequency='d', adjustflag='2'
        )
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        if len(data) < 180:
            continue
        df = pd.DataFrame(data, columns=rs.fields)
        for col in ['open','high','low','close','volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        hh180 = df.tail(180)['high'].max()
        ll180 = df.tail(180)['low'].min()
        ratio = hh180 / ll180 if ll180 > 0 else 999
        latest = df.iloc[-1]
        close = latest['close']

        if ratio < 1.5 and close <= 39 and close >= 1:
            mkt_cap = fundamental_cache.get(code, 0)
            当前符合.append({
                'code': code, 'name': name,
                'close': close, 'ratio': ratio, 'mkt_cap': mkt_cap,
            })
    except:
        continue

bs.logout()

df_current = pd.DataFrame(当前符合).sort_values('ratio')

tech_filter = df_current[df_current['close'] <= 39]
print(f"\n技术条件满足（180日区间<50% + 股价<=39元）: {len(tech_filter)} 只")
print(f"\n{'代码':<8} {'名称':<10} {'现价':>6} {'180日区间':>10} {'市值(亿)':>10}")
print("-" * 50)
for _, r in tech_filter.head(30).iterrows():
    mkt_str = f"{r['mkt_cap']:.0f}" if r['mkt_cap'] > 0 else "N/A"
    print(f"{r['code']:<8} {r['name']:<10} {r['close']:>6.2f} {r['ratio']:>10.3f} {mkt_str:>10}")

mkt_sub = tech_filter[(tech_filter['mkt_cap'] > 0) & (tech_filter['mkt_cap'] <= 300)]
print(f"\n市值<=300亿子集: {len(mkt_sub)} 只")
for _, r in mkt_sub.iterrows():
    print(f"  {r['code']} {r['name']:<8} 价:{r['close']:.2f} 区间:{r['ratio']:.3f} 市值:{r['mkt_cap']:.0f}亿")

# ═══ 6. 通达信公式 ═══
print(f"\n{'='*55}")
print(f"【通达信指标公式源码】复制到公式管理器")
print(f"{'='*55}")
formula = """{低波震荡 - 180日区间震荡选股指标}
{参数：无}
{使用：条件选股 / 指标叠加主图}

HH180:=HHV(HIGH,180);
LL180:=LLV(LOW,180);
区间幅度:HH180/LL180;
条件区间50:(区间幅度<1.5);
条件价格39:C<=39;
低波震荡:条件区间50 AND 条件价格39;

STICKLINE(低波震荡=1,HIGH+0.05,HIGH-0.05,2,0),COLORFF00FF;
DRAWTEXT(低波震荡=1 AND CURRBARSCOUNT<=30,LOW-0.1,'低波'),COLORFF00FF;"""
print(formula)
