import subprocess, json, pandas as pd, baostock as bs
from datetime import datetime, timedelta

def curl_json(url, timeout=25):
    try:
        r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True, timeout=timeout)
        return json.loads(r.stdout)
    except:
        return {}

all_stocks = []
for page in range(1, 6):
    url = (f"https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn={page}&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
        f"&fltt=2&invt=2&fid=f3&fs=m:0+t:2,m:1+t:2"
        f"&fields=f12,f14,f2,f3,f5,f6,f8,f62,f184")
    r = curl_json(url)
    if r.get('data') and r['data'].get('diff'):
        all_stocks.extend(r['data']['diff'])
    else:
        break

stocks = []
for item in all_stocks:
    stocks.append({
        'code': str(item.get('f12','')),
        'name': item.get('f14',''),
        'price': item.get('f2',0)/100,
        'pct': item.get('f3',0)/100,
        'vol': item.get('f5',0),
        'amount': item.get('f6',0),
        'turn': item.get('f8',0)/100,
        'main_force': item.get('f62',0),
        'main_ratio': item.get('f184',0)/100
    })

df = pd.DataFrame(stocks)
df = df.drop_duplicates(subset='code')
df['amount_wan'] = df['amount'] / 10000
df['main_force_wan'] = df['main_force'] / 10000
print(f"全市场 {len(df)} 只，今日涨幅均值: {df['pct'].mean():.2f}%")

# 筛选强势股
cond = (df['pct'] > 1) & (df['turn'] >= 2) & (df['turn'] <= 10) & (df['main_force'] > 10000000) & (df['amount'] > 20000000)
df_s = df[cond].sort_values('main_force_wan', ascending=False)
print(f"\n强势股（涨>1% + 换手2~10% + 主力净流入>1000万 + 成交额>2000万）: {len(df_s)} 只")
print(df_s[['code','name','price','pct','turn','amount_wan','main_force_wan','main_ratio']].head(20).to_string(index=False))

# ===== 对强势股进行深度技术分析 =====
bs.login()
top_codes = df_s.head(15)['code'].tolist()

def trend_arrow(t):
    return "↑" if t > 0 else "↓" if t < 0 else "→"

print("\n=== 强势股技术面深度分析 ===")
results = []

for code in top_codes:
    prefix = 'sz' if code.startswith(('0','2','3')) else 'sh'
    try:
        rs = bs.query_history_k_data_plus(f'{prefix}.{code}',
            'date,open,high,low,close,volume,pctChg,turn',
            start_date=(datetime.today()-timedelta(days=25)).strftime('%Y-%m-%d'),
            end_date=datetime.today().strftime('%Y-%m-%d'),
            frequency='d', adjustflag='2')
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        d = pd.DataFrame(data, columns=rs.fields)
        for col in ['open','high','low','close','volume','pctChg','turn']:
            d[col] = pd.to_numeric(d[col], errors='coerce')
        d['date'] = pd.to_datetime(d['date'])
        d = d.sort_values('date').reset_index(drop=True)

        ma5 = d['close'].rolling(5).mean().iloc[-1]
        ma10 = d['close'].rolling(10).mean().iloc[-1]
        ma20 = d['close'].rolling(20).mean().iloc[-1]
        close = d['close'].iloc[-1]

        # RSI6
        delta = d['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(6).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(6).mean().iloc[-1]
        rsi6 = 100 - (100 / (1 + gain/(loss+0.0001)))

        # 近5日量价
        recent5 = d.tail(5)
        price_trend = recent5['close'].iloc[-1] - recent5['close'].iloc[0]
        vol_trend = recent5['volume'].iloc[-1] - recent5['volume'].iloc[0]
        div = (price_trend > 0 and vol_trend < 0)
        vol_ratio = d['volume'].iloc[-1] / d['volume'].rolling(5).mean().iloc[-1]

        # 倍量日
        vol_ratios = d['volume'] / d['volume'].shift(1)
        max_ratio = vol_ratios.max()
        max_vol_idx = vol_ratios.idxmax()
        max_vol_row = d.loc[max_vol_idx]

        # 均线多头
        ma_arr = '多头' if ma5 > ma10 > ma20 else '缠绕'

        # MACD
        dif = d['close'].ewm(span=12).mean() - d['close'].ewm(span=26).mean()
        dea = dif.ewm(span=9).mean()
        macd = (dif - dea) * 2
        macd_last = macd.iloc[-1]

        # 5日均换手
        turn5avg = recent5['turn'].mean()

        # 20日位置
        high20 = d['high'].tail(20).max()
        low20 = d['low'].tail(20).min()
        pos_20d = (close - low20) / (high20 - low20 + 0.001)

        # 60日均线
        ma60 = d['close'].rolling(60).mean().iloc[-1] if len(d) >= 60 else 0
        above_ma60 = close > ma60 if ma60 > 0 else None

        row_info = {
            'code': code,
            'name': recent5['close'].iloc[0],  # just placeholder
            'close': close,
            'pct': d['pctChg'].iloc[-1],
            'rsi6': rsi6,
            'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
            'ma_arr': ma_arr,
            'macd': macd_last,
            'above_ma60': above_ma60,
            'div': div,
            'vol_ratio': vol_ratio,
            'max_vol_date': max_vol_row['date'],
            'max_vol_pct': max_vol_row['pctChg'],
            'max_vol_ratio': max_ratio,
            'turn5avg': turn5avg,
            'pos_20d': pos_20d
        }
        results.append(row_info)

        print(f"\n{'='*50}")
        print(f"{code} | 多头:{ma_arr} | MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f}")
        print(f"  收盘:{close:.2f} 涨跌:{d['pctChg'].iloc[-1]:+.2f}% RSI6={rsi6:.1f} MACD={macd_last:.4f}({'红' if macd_last>0 else '绿'})")
        print(f"  倍量日:{max_vol_row['date'].strftime('%m/%d')} 量{max_vol_row['volume']/1e4:.0f}万({max_ratio:.1f}倍) 涨{max_vol_row['pctChg']:+.1f}%")
        print(f"  量价背离={div} 量比={vol_ratio:.2f} 5日均换手={turn5avg:.2f}%")
        print(f"  60日线上方:{above_ma60} 20日位置:{pos_20d:.0%}")
    except Exception as e:
        print(f"\n{code} 数据获取失败: {e}")

bs.logout()

# 综合评分排名
print("\n\n=== 综合评分排名（技术面）===")
# 评分维度：多头排列、RSI适中、倍量拉升、量价背离、60日线上方、20日位置适中
for r in results:
    score = 0
    if r['ma_arr'] == '多头': score += 25
    if 40 < r['rsi6'] < 70: score += 20  # RSI适中（不过高不过低）
    elif r['rsi6'] <= 40: score += 10  # 偏低是好事
    if r['macd'] > 0: score += 15
    if r['above_ma60']: score += 15
    if r['div']: score += 10  # 量价背离=主力控盘
    if 0.3 < r['pos_20d'] < 0.8: score += 15  # 20日位置适中
    
    # 附加：近5日有倍量
    if r['max_vol_ratio'] >= 2.0 and r['max_vol_pct'] > 2:
        score += 10
    
    pct_score = min(r['pct'] * 3, 15)  # 涨幅给分，上限15
    score += pct_score
    
    r['score'] = score

results_sorted = sorted(results, key=lambda x: x['score'], reverse=True)
print("\n排名  代码     收盘   涨跌   RSI6   均线  MACD  60日线  量价背离  量比  评分")
for i, r in enumerate(results_sorted, 1):
    print(f"  {i:2d}  {r['code']}  {r['close']:.2f}  {r['pct']:+.2f}%  {r['rsi6']:5.1f}   {r['ma_arr']}  {r['macd']:+.4f}   {r['above_ma60']}   {r['div']}   {r['vol_ratio']:.2f}  {r['score']:3.0f}")