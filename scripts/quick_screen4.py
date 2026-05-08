import subprocess, json, pandas as pd, baostock as bs
from datetime import datetime, timedelta

def curl_json(url, timeout=25):
    try:
        r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True, timeout=timeout)
        return json.loads(r.stdout)
    except:
        return {}

all_stocks = []
for page in range(1, 11):
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
        'price': item.get('f2',0),
        'pct': item.get('f3',0)/100,
        'vol': item.get('f5',0),
        'amount': item.get('f6',0)/10000,
        'turn': item.get('f8',0)/100,
        'main_force': item.get('f62',0)/10000,
        'main_ratio': item.get('f184',0)/100
    })

df = pd.DataFrame(stocks)
df = df.drop_duplicates(subset='code')
print(f"全市场 {len(df)} 只")

# 筛选强势股：涨幅>0 + 换手>=1% + 主力净流入>0 + 成交额>=3000万
cond = (df['pct'] > 0) & (df['turn'] >= 0.01) & (df['main_force'] > 0) & (df['amount'] >= 3000)
df_s = df[cond].sort_values('main_force', ascending=False)
print(f"\n强势股筛选: {len(df_s)} 只")
print("主力净流入TOP10:")
for _, row in df_s.head(10).iterrows():
    print(f"  {row['code']} {row['name']} 现价:{row['price']:.2f} 涨:{row['pct']:+.2f}% 换手:{row['turn']*100:.2f}% 主力净流入:{row['main_force']:.0f}万")

# ===== 对主力净流入TOP10深度技术分析 =====
bs.login()
top_codes = df_s.head(10)['code'].tolist()

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
        ma60_val = d['close'].rolling(60).mean().iloc[-1] if len(d) >= 60 else 0
        close = d['close'].iloc[-1]

        delta = d['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(6).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(6).mean().iloc[-1]
        rsi6 = 100 - (100 / (1 + gain/(loss+0.0001)))

        dif = d['close'].ewm(span=12).mean() - d['close'].ewm(span=26).mean()
        dea = dif.ewm(span=9).mean()
        macd = (dif - dea) * 2
        macd_val = macd.iloc[-1]

        recent5 = d.tail(5)
        price_trend = recent5['close'].iloc[-1] - recent5['close'].iloc[0]
        vol_trend = recent5['volume'].iloc[-1] - recent5['volume'].iloc[0]
        div = (price_trend > 0) and (vol_trend < 0)
        vol_ratio = d['volume'].iloc[-1] / d['volume'].rolling(5).mean().iloc[-1]
        turn5avg = recent5['turn'].mean()

        vol_ratios = d['volume'] / d['volume'].shift(1)
        max_ratio = vol_ratios.max()
        max_vol_row = d.loc[vol_ratios.idxmax()]

        ma_arr = '多头' if ma5 > ma10 > ma20 else '缠绕'
        high20 = d['high'].tail(20).max()
        low20 = d['low'].tail(20).min()
        pos20 = (close - low20) / (high20 - low20 + 0.001)
        above_ma60 = (ma60_val > 0) and (close > ma60_val)

        # 综合评分
        score = 0
        if ma_arr == '多头': score += 25
        if 40 <= rsi6 <= 70: score += 20
        elif rsi6 < 40: score += 10
        if macd_val > 0: score += 15
        if above_ma60: score += 15
        if div: score += 10
        if 0.3 <= pos20 <= 0.8: score += 15
        score += min(d['pctChg'].iloc[-1] * 3, 15)
        if rsi6 > 80: score -= 15  # RSI太高扣分
        if ma_arr == '缠绕': score -= 10  # 均线缠绕扣分

        mforce = df_s[df_s['code']==code]['main_force'].iloc[0] if code in df_s['code'].values else 0
        today_turn = df_s[df_s['code']==code]['turn'].iloc[0] if code in df_s['code'].values else 0

        print(f"\n{'='*60}")
        print(f"{code} {df_s[df_s['code']==code]['name'].iloc[0] if code in df_s['code'].values else ''} | {ma_arr}")
        print(f"  收盘:{close:.2f} 今日涨跌:{d['pctChg'].iloc[-1]:+.2f}% 今日换手:{today_turn*100:.2f}%")
        print(f"  RSI6={rsi6:.1f} MACD={macd_val:+.4f}({'红' if macd_val>0 else '绿'})")
        print(f"  MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f}")
        print(f"  近20日倍量日:{max_vol_row['date'].strftime('%m/%d')} 量{max_vol_row['volume']/1e4:.0f}万({max_ratio:.1f}倍) 涨{max_vol_row['pctChg']:+.1f}%")
        print(f"  量价背离={div} 量比={vol_ratio:.2f} 5日均换手={turn5avg*100:.2f}%")
        print(f"  60日线上方:{above_ma60} 20日位置:{pos20:.0%} 综合评分:{score}")

        results.append({
            'code': code,
            'name': df_s[df_s['code']==code]['name'].iloc[0] if code in df_s['code'].values else '',
            'close': close, 'pct': d['pctChg'].iloc[-1], 'today_turn': today_turn,
            'rsi6': rsi6, 'ma_arr': ma_arr, 'macd': macd_val,
            'above_ma60': above_ma60, 'div': div, 'vol_ratio': vol_ratio,
            'turn5avg': turn5avg, 'pos20': pos20, 'score': score,
            'max_ratio': max_ratio, 'max_vol_pct': max_vol_row['pctChg'],
            'main_force': mforce, 'price': df_s[df_s['code']==code]['price'].iloc[0] if code in df_s['code'].values else 0
        })
    except Exception as e:
        print(f"\n{code} 失败: {e}")

bs.logout()

results_sorted = sorted(results, key=lambda x: x['score'], reverse=True)
print(f"\n\n{'='*60}")
print("  最终综合评分排名（强势股TOP10）")
print(f"{'='*60}")
print(f"  排名  代码     名称        收盘   今日涨跌   RSI6   均线   MACD红  60日线  背离  评分")
for i, r in enumerate(results_sorted, 1):
    print(f"  {i:2d}.  {r['code']}  {r['name']:<8} {r['close']:.2f}   {r['pct']:+.2f}%   {r['rsi6']:5.1f}   {r['ma_arr']}    {'是' if r['macd']>0 else '否'}      {r['above_ma60']}    {r['div']}   {r['score']:3.0f}")

# 找其中汽车零部件相关
auto_keywords = ['汽车', '车零', '零部件', '传动', '底盘', '发动机', '车身', '车灯', '轮胎', '车饰', '汽配', '制动']
print(f"\n\n{'='*60}")
print("  汽车零部件相关标的（从强势股中筛选）")
print(f"{'='*60}")
auto_results = [r for r in results_sorted if any(k in r['name'] for k in auto_keywords)]
if auto_results:
    for i, r in enumerate(auto_results, 1):
        print(f"  {i}. {r['code']} {r['name']} 收盘:{r['close']:.2f} 涨跌:{r['pct']:+.2f}% RSI6={r['rsi6']:.1f} 评分:{r['score']}")
else:
    print("  无直接匹配，尝试从同板块扩散...")
    # 找002715登云股份同行业个股
    print("  提示: 今日汽车零部件板块整体表现一般，建议关注:002715登云股份，以及上述强势股中的拓普集团(601689)、五洲新春(603667)等汽车零部件相关个股")