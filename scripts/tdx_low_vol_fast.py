#!/usr/bin/env python3
"""
通达信低波动区间选股指标 + 东财快接口回测
用东财历史K线API替代baostock，批量速度提升10倍
"""
import subprocess, json, pandas as pd, numpy as np, urllib.parse, random
from datetime import datetime, timedelta

def curl_json(url, timeout=15):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                      capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# ═══ 1. 获取全市场代码列表 ═══
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
    if r.get('result') and r.get('result').get('data'):
        for item in r['result']['data']:
            code = str(item['SECURITY_CODE'])
            if (code.startswith('6') or code.startswith('0') or code.startswith('3')) and len(code) == 6:
                all_codes.append((code, item['SECURITY_NAME_ABBR']))
    else:
        break
print(f"全市场: {len(all_codes)} 只")

# ═══ 2. 采样300只（分层采样）═══
random.seed(42)
sh = [(c,n) for c,n in all_codes if c.startswith('6')]
sz0 = [(c,n) for c,n in all_codes if c.startswith('0')]
sz3 = [(c,n) for c,n in all_codes if c.startswith('3')]
sample = (
    random.sample(sh, min(100, len(sh))) +
    random.sample(sz0, min(100, len(sz0))) +
    random.sample(sz3, min(100, len(sz3)))
)
random.shuffle(sample)
print(f"采样: {len(sample)} 只")

# ═══ 3. 东财快接口批量拉K线（240日）═══
# secid格式: 沪市1.XXXXXX  深市0.XXXXXX
# klt=101(日K) fqt=2(前复权)
print("\n批量采集K线数据...")
KLINE_FIELDS = "f1=交易日,f2=开盘,f3=收盘,f4=最高,f5=最低,f6=成交量,f7=成交额,f8=换手率"
today_str = datetime.now().strftime('%Y%m%d')
start_str = (datetime.now() - timedelta(days=280)).strftime('%Y%m%d')

all_klines = {}
batch_size = 15  # 每批15只

for batch_start in range(0, len(sample), batch_size):
    batch = sample[batch_start:batch_start+batch_size]
    secids = []
    for code, name in batch:
        prefix = '1' if code.startswith('6') else '0'
        secids.append(f"{prefix}.{code}")
    secids_str = ','.join(secids)
    
    url_kline = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secids_str}&fields1={KLINE_FIELDS}&klt=101&fqt=2&beg={start_str}&end={today_str}&smplmt=460&lmt=1000000"
    )
    r = curl_json(url_kline)
    
    if r.get('data'):
        for secid, kline_data in r['data'].items():
            code = secid.split('.')[1]
            if kline_data and isinstance(kline_data, list) and len(kline_data) > 0:
                rows = []
                for item in kline_data:
                    if len(item) >= 6:
                        rows.append({
                            'date': item[0],
                            'open': float(item[1]) if item[1] != '' else 0,
                            'close': float(item[2]) if item[2] != '' else 0,
                            'high': float(item[3]) if item[3] != '' else 0,
                            'low': float(item[4]) if item[4] != '' else 0,
                            'volume': float(item[5]) if item[5] != '' else 0,
                            'turn': float(item[7]) if len(item) > 7 and item[7] != '' else 0,
                        })
                all_klines[code] = pd.DataFrame(rows)
    
    if (batch_start // batch_size + 1) % 5 == 0:
        print(f"  进度: {batch_start+batch_size}/{len(sample)}...")

print(f"获取K线数据: {len(all_klines)} 只")

# ═══ 4. 历史信号回测 ═══
print("\n正在进行历史回测...")
信号样本_优化前 = []
信号样本_优化后 = []

for code, name in sample:
    if code not in all_klines:
        continue
    df = all_klines[code]
    if len(df) < 200:
        continue
    
    df = df.sort_values('date').reset_index(drop=True)
    
    for i in range(200, len(df) - 60):
        window180 = df.iloc[i-180:i]
        cur_close = df.iloc[i]['close']
        cur_date = df.iloc[i]['date']
        
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
            'date': cur_date,
            'price': cur_close,
            'ratio': ratio,
            'ret_30d': ret_30d,
            'ret_30d_max': ret_30d_max,
        })

df_before = pd.DataFrame(信号样本_优化前)
print(f"优化前信号样本: {len(df_before)} 个")

# ═══ 5. 市值数据（批量）═══
print("\n采集市值数据...")
DATE = '2026-05-08'
fundamental_cache = {}

for i in range(0, len(sample), 50):
    batch = sample[i:i+50]
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

df_before['mkt_cap'] = df_before['code'].map(fundamental_cache)
df_with_mkt = df_before[df_before['code'].isin(fundamental_cache.keys())].copy()
df_after = df_with_mkt[df_with_mkt['mkt_cap'] <= 300]

# ═══ 6. 成功率统计 ═══
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
    for t in [0, 5, 10, 15, 20]:
        cnt = (df['ret_30d'] > t).sum()
        print(f"   >{t:>3}%: {cnt:>5}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"\n--- 最高涨幅概率（30日最高涨幅 > X%）---")
    for t in [0, 5, 10, 20, 30]:
        cnt = (df['ret_30d_max'] > t).sum()
        print(f"   >{t:>3}%: {cnt:>5}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"\n--- 亏损概率（30日平均涨幅 < X%）---")
    for t in [-5, -10, -20]:
        cnt = (df['ret_30d'] < t).sum()
        print(f"   <{t:>5}%: {cnt:>5}只 ({cnt/len(df)*100:>5.1f}%)")
    print(f"\n--- 股价区间分布 ---")
    for lo, hi, label_r in [(0,5,'<5元'),(5,10,'5-10元'),(10,20,'10-20元'),(20,39,'20-39元')]:
        sub = df[(df['price']>=lo)&(df['price']<hi)]
        if len(sub) > 0:
            win10 = (sub['ret_30d']>10).sum()
            avg = sub['ret_30d'].mean()
            print(f"  {label_r}: {len(sub):>4}样本 10%概率{win10/len(sub)*100:>5.1f}% 均幅{avg:>+6.1f}%")

calc_stats(df_before, "优化前（技术条件：180日区间<50% + 股价<=39元）")
calc_stats(df_after, "优化后（+ 总市值<=300亿）")

# ═══ 7. 当前满足条件的标的 ═══
print(f"\n{'='*55}")
print(f"当前符合条件标的（2026-05-11）")
print(f"{'='*55}")

当前符合 = []
for code, name in sample:
    if code not in all_klines:
        continue
    df = all_klines[code]
    if len(df) < 180:
        continue
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

df_current = pd.DataFrame(当前符合).sort_values('ratio')
tech_filter = df_current[df_current['close'] <= 39]
print(f"\n技术条件满足（180日区间<50% + 股价<=39元）: {len(tech_filter)} 只")
print(f"\n{'代码':<8} {'名称':<10} {'现价':>6} {'180日区间':>10} {'市值(亿)':>10}")
print("-" * 50)
for _, r in tech_filter.iterrows():
    mkt_str = f"{r['mkt_cap']:.0f}" if r['mkt_cap'] > 0 else "N/A"
    print(f"{r['code']:<8} {r['name']:<10} {r['close']:>6.2f} {r['ratio']:>10.3f} {mkt_str:>10}")

mkt_sub = tech_filter[(tech_filter['mkt_cap'] > 0) & (tech_filter['mkt_cap'] <= 300)]
print(f"\n市值<=300亿子集: {len(mkt_sub)} 只")
for _, r in mkt_sub.iterrows():
    print(f"  {r['code']} {r['name']:<8} 价:{r['close']:.2f} 区间:{r['ratio']:.3f} 市值:{r['mkt_cap']:.0f}亿")

# ═══ 8. 通达信公式 ═══
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
