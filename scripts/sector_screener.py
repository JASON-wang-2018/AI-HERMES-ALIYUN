import subprocess, json, pandas as pd, baostock as bs
from datetime import datetime, timedelta

def curl_json(url, timeout=30):
    try:
        r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True, timeout=timeout)
        return json.loads(r.stdout)
    except:
        return {}

# 采集全市场A股 - 分页获取
all_stocks = []
for page in range(1, 6):  # 获取5页，每页100只，共500只
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
        'amount': item.get('f6',0)/10000,  # 万元
        'turn': item.get('f8',0)/100,
        'main_force': item.get('f62',0)/10000,  # 万元
        'main_ratio': item.get('f184',0)/100
    })

df = pd.DataFrame(stocks)
df = df.drop_duplicates(subset='code')
print(f"全市场 {len(df)} 只个股")

# 放宽条件：涨幅>1% + 换手2~8% + 主力净流入>1000万
cond = (df['pct'] > 1) & (df['turn'] >= 2) & (df['turn'] <= 8) & (df['main_force'] > 0.1) & (df['amount'] > 2000)
df_strong = df[cond].sort_values('main_force', ascending=False)
print(f"\n强势股筛选（涨>1% + 换手2~8% + 主力净流入>1000万 + 成交额>2000万）:")
print(f"共 {len(df_strong)} 只")
print(df_strong[['code','name','price','pct','turn','main_force','main_ratio']].head(20).to_string(index=False))

# 对前10只强势股进行深度技术分析
bs.login()
top_codes = df_strong.head(10)['code'].tolist()

def trend_arrow(t):
    return "↑" if t > 0 else "↓" if t < 0 else "→"

print("\n=== TOP10强势股技术面深度分析 ===")
for code in top_codes:
    prefix = 'sz' if code.startswith(('0','2','3')) else 'sh'
    try:
        rs = bs.query_history_k_data_plus(f'{prefix}.{code}',
            'date,open,high,low,close,volume,pctChg,turn',
            start_date=(datetime.today()-timedelta(days=20)).strftime('%Y-%m-%d'),
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
        vol_5avg = recent5['volume'].mean()
        vol_ratio = d['volume'].iloc[-1] / d['volume'].rolling(5).mean().iloc[-1]

        # 倍量日
        vol_ratios = d['volume'] / d['volume'].shift(1)
        max_ratio = vol_ratios.max()
        max_vol_row = d.loc[vol_ratios.idxmax()]

        # 均线多头
        ma_arr = '多头' if ma5 > ma10 > ma20 else '空头' if ma5 < ma10 < ma20 else '缠绕'

        print(f"\n{code} {d['close'].iloc[0]:.0f} {ma_arr}")
        print(f"  现价:{close:.2f} 涨:{d['pctChg'].iloc[-1]:+.2f}% RSI6={rsi6:.1f}")
        print(f"  MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f}")
        print(f"  倍量日:{max_vol_row['date'].strftime('%m/%d')} 量{max_vol_row['volume']/1e4:.0f}万({vol_ratios.max():.1f}倍) 收{max_vol_row['close']:.2f}({max_vol_row['pctChg']:+.1f}%)")
        print(f"  5日量价: 价{trend_arrow(price_trend)} 量{trend_arrow(vol_trend)} 量价背离={div} 量比={vol_ratio:.2f}")
        print(f"  5日均换手:{recent5['turn'].mean():.2f}%")
    except Exception as e:
        print(f"\n{code} 数据获取失败: {e}")

bs.logout()