#!/usr/bin/env python3
"""
通达信低波动区间选股指标 + 最简回测（100只股票）
"""
import subprocess, json, pandas as pd, numpy as np, baostock as bs, urllib.parse, random
from datetime import datetime, timedelta

def curl_json(url, timeout=20):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                      capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# 获取全市场代码
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
    if r.get('result') and r['result'].get('data'):
        for item in r['result']['data']:
            code = str(item['SECURITY_CODE'])
            if (code.startswith('6') or code.startswith('0') or code.startswith('3')) and len(code) == 6:
                all_codes.append((code, item['SECURITY_NAME_ABBR']))
    else:
        break
print(f"全市场: {len(all_codes)} 只")

# 采样100只
random.seed(2026)
sample = random.sample(all_codes, min(100, len(all_codes)))
print(f"采样: {len(sample)} 只")

# 历史回测
print("\n历史回测...")
bs.login()
today_str = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=450)).strftime('%Y-%m-%d')

信号样本_优化前 = []
信号样本_优化后 = []

for code, name in sample:
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
            hh180 = window180['high'].max()
            ll180 = window180['low'].min()
            ratio = hh180 / ll180 if ll180 > 0 else 999
            if ratio >= 1.5 or cur_close > 39 or cur_close < 1:
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
                'price': cur_close, 'ratio': ratio,
                'ret_30d': ret_30d, 'ret_30d_max': ret_30d_max,
            })
    except:
        continue

bs.logout()

# 市值数据
print("采集市值数据...")
DATE = '2026-05-08'
fundamental_cache = {}
for code, _ in sample:
    FILTER_V = f"(TRADE_DATE='{DATE}')(SECURITY_CODE={code})"
    url_val = (
        "https://datacenter.eastmoney.com/api/data/v1/get"
        "?reportName=RPT_VALUEANALYSIS_DET"
        "&columns=SECURITY_CODE,TOTAL_MARKET_CAP"
        "&pageNumber=1&pageSize=1"
        f"&filter={urllib.parse.quote(FILTER_V)}&source=WEB&client=WEB"
    )
    rv = curl_json(url_val)
    if rv.get('result') and rv['result'].get('data'):
        fundamental_cache[code] = rv['result']['data'][0].get('TOTAL_MARKET_CAP', 0) / 1e8

# 映射市值
df_before = pd.DataFrame(信号样本_优化前)
df_before['mkt_cap'] = df_before['code'].map(fundamental_cache)
df_with_mkt = df_before[df_before['code'].isin(fundamental_cache.keys())]
df_after = df_with_mkt[df_with_mkt['mkt_cap'] <= 300]

# 统计
def calc_stats(df, label):
    if len(df) == 0:
        print(f"\n{label}: 无样本"); return
    print(f"\n{'='*55}")
    print(f"{label}")
    print(f"{'='*55}")
    print(f"总信号: {len(df)} 个  平均30日涨幅: {df['ret_30d'].mean():+.2f}%  中位数: {df['ret_30d'].median():+.2f}%")
    print(f"\n盈利概率（30日均幅 > X%）:")
    for t in [0, 5, 10, 15, 20]:
        cnt = (df['ret_30d'] > t).sum()
        print(f"   >{t:>3}%: {cnt:>4}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"最高涨幅概率（30日最高 > X%）:")
    for t in [0, 5, 10, 20, 30]:
        cnt = (df['ret_30d_max'] > t).sum()
        print(f"   >{t:>3}%: {cnt:>4}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"亏损概率（30日均幅 < X%）:")
    for t in [-5, -10, -20]:
        cnt = (df['ret_30d'] < t).sum()
        print(f"   <{t:>5}%: {cnt:>4}只 ({cnt/len(df)*100:>5.1f}%)")

calc_stats(df_before, "优化前（180日区间<50% + 股价<=39元）")
calc_stats(df_after, "优化后（+ 总市值<=300亿）")

# 当前标的
print(f"\n{'='*55}")
print(f"当前符合条件标的（2026-05-11）")
print(f"{'='*55}")
bs.login()
当前符合 = []
for code, name in sample:
    prefix = 'sh' if code.startswith('6') else 'sz'
    try:
        rs = bs.query_history_k_data_plus(
            f'{prefix}.{code}',
            'date,open,high,low,close',
            start_date=(datetime.now()-timedelta(days=250)).strftime('%Y-%m-%d'),
            end_date=today_str, frequency='d', adjustflag='2')
        data = []
        while rs.next(): data.append(rs.get_row_data())
        if len(data) < 180: continue
        df = pd.DataFrame(data, columns=rs.fields)
        for col in ['open','high','low','close']: df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.sort_values('date').reset_index(drop=True)
        hh180 = df.tail(180)['high'].max()
        ll180 = df.tail(180)['low'].min()
        ratio = hh180/ll180 if ll180 > 0 else 999
        close = df.iloc[-1]['close']
        if ratio < 1.5 and 1 <= close <= 39:
            mkt = fundamental_cache.get(code, 0)
            当前符合.append({'code':code,'name':name,'close':close,'ratio':ratio,'mkt_cap':mkt})
    except: continue
bs.logout()

df_c = pd.DataFrame(当前符合)
if len(df_c) > 0:
    df_c = df_c.sort_values('ratio')
    print(f"\n技术条件满足: {len(df_c)} 只")
    for _, r in df_c.iterrows():
        m = f"{r['mkt_cap']:.0f}" if r['mkt_cap'] > 0 else "N/A"
        print(f"  {r['code']} {r['name']:<8} 价:{r['close']:.2f} 区间:{r['ratio']:.3f} 市值:{m}亿")
    mkt_sub = df_c[(df_c['mkt_cap']>0)&(df_c['mkt_cap']<=300)]
    print(f"\n市值<=300亿: {len(mkt_sub)} 只")
    for _, r in mkt_sub.iterrows():
        print(f"  {r['code']} {r['name']:<8} 价:{r['close']:.2f} 区间:{r['ratio']:.3f} 市值:{r['mkt_cap']:.0f}亿")
else:
    print(f"\n技术条件满足: 0 只（采样100只中无标的）")
    print("建议扩大采样或换时间段重测")

print(f"\n{'='*55}")
print("【通达信指标公式源码】复制到公式管理器")
print("="*55)
print("""{低波震荡 - 180日区间震荡选股指标}
{参数：无}
{使用：条件选股 / 指标叠加主图}

HH180:=HHV(HIGH,180);
LL180:=LLV(LOW,180);
区间幅度:HH180/LL180;
条件区间50:(区间幅度<1.5);
条件价格39:C<=39;
低波震荡:条件区间50 AND 条件价格39;

STICKLINE(低波震荡=1,HIGH+0.05,HIGH-0.05,2,0),COLORFF00FF;
DRAWTEXT(低波震荡=1 AND CURRBARSCOUNT<=30,LOW-0.1,'低波'),COLORFF00FF;""")
