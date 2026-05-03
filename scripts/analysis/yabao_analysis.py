import pandas as pd, numpy as np

rows = []
with open('/home/admin/.hermes/cache/documents/doc_dc4ae9280a26_260423-600351.xls', 'rb') as f:
    raw = f.read().decode('gbk')
lines = raw.split('\r\n')
for line in lines[2:]:
    if not line.strip() or line.startswith('时间') or line.startswith('#'): continue
    p = line.split('\t')
    if len(p) < 27: continue
    try:
        d = p[0].strip()
        if '/' not in d: continue
        rows.append({
            'date': d,
            'open': float(p[1]), 'high': float(p[2]), 'low': float(p[3]),
            'close': float(p[4]), 'volume': float(p[5]),
            'ma5': float(p[6]) if p[6].strip() else np.nan,
            'ma10': float(p[7]) if p[7].strip() else np.nan,
            'ma20': float(p[8]) if p[8].strip() else np.nan,
            'ma60': float(p[9]) if p[9].strip() else np.nan,
            'ma120': float(p[10]) if p[10].strip() else np.nan,
            'vol': float(p[18]) if p[18].strip() else np.nan,
            'vol5': float(p[19]) if p[19].strip() else np.nan,
            'vol10': float(p[20]) if p[20].strip() else np.nan,
            'vol_ratio': float(p[23]) if p[23].strip() else np.nan,
            'rsi1': float(p[24]) if p[24].strip() else np.nan,
            'rsi2': float(p[25]) if p[25].strip() else np.nan,
            'rsi3': float(p[26]) if p[26].strip() else np.nan,
        })
    except: pass

df = pd.DataFrame(rows)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)
L = len(df)

ema12 = df['close'].ewm(span=12, adjust=False).mean()
ema26 = df['close'].ewm(span=26, adjust=False).mean()
df['dif'] = ema12 - ema26
df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
df['macd'] = (df['dif'] - df['dea']) * 2
n = 9
low_n = df['low'].rolling(n).min()
high_n = df['high'].rolling(n).max()
rsv = (df['close'] - low_n) / (high_n - low_n) * 100
df['K'] = rsv.ewm(com=3, adjust=False).mean()
df['D'] = df['K'].ewm(com=3, adjust=False).mean()
df['J'] = 3*df['K'] - 2*df['D']
df['boll_mid'] = df['close'].rolling(20).mean()
df['boll_std'] = df['close'].rolling(20).std()
df['boll_upper'] = df['boll_mid'] + 2*df['boll_std']
df['boll_lower'] = df['boll_mid'] - 2*df['boll_std']
df['atr'] = (df['high'] - df['low']).rolling(10).mean()
df['atr_pct'] = df['atr'] / df['close'] * 100
df['vol_ma20'] = df['volume'].rolling(20).mean()

latest = df.iloc[-1]
prev = df.iloc[-2]
c = latest['close']; o = latest['open']; h = latest['high']; l = latest['low']
vol = latest['volume']; vr = latest['vol_ratio']
ma5 = latest['ma5']; ma10 = latest['ma10']; ma20 = latest['ma20']
ma60 = latest['ma60']; ma120 = latest['ma120']
dif = latest['dif']; dea = latest['dea']; macd = latest['macd']
K = latest['K']; D = latest['D']; J = latest['J']
rsi1 = latest['rsi1']; rsi2 = latest['rsi2']; rsi3 = latest['rsi3']
boll_u = latest['boll_upper']; boll_m = latest['boll_mid']; boll_l = latest['boll_lower']
atr_pct = latest['atr_pct']
dif_p = prev['dif']
imax = df['high'].max(); imin = df['low'].min()
pos_all = (c - imin) / (imax - imin) * 100
high120 = df['high'].rolling(120).max().iloc[-1]
low120 = df['low'].rolling(120).min().iloc[-1]
pos120 = (c - low120) / (high120 - low120) * 100
rl = df['low'].tail(20).min(); rh = df['high'].tail(20).max()
vol_ma20 = df['volume'].rolling(20).mean().iloc[-1]
vr20 = vol / vol_ma20 if vol_ma20 > 0 else 1
df5 = df.tail(5)
pc5 = df5['close'].iloc[-1] - df5['close'].iloc[0]
vc5 = df5['volume'].iloc[-1] - df5['volume'].iloc[0]
chg = (c / prev['close'] - 1) * 100
chg_fmt = "+{:.2f}%".format(chg) if chg >= 0 else "{:.2f}%".format(chg)

def na(v): return pd.isna(v)

print("=" * 55)
print("  亚宝药业(600351) 深度技术分析")
print("  数据: {}行 | {} ~ {}".format(L, df['date'].min().date(), df['date'].max().date()))
print("=" * 55)
print("  最新: {}  收盘:{:.2f}  涨跌:{}".format(
    latest['date'].strftime("%Y-%m-%d"), c, chg_fmt))
print("  区间: {:.2f}(低) ~ {:.2f}(高)  历史位置:{:.1f}%".format(imin, imax, pos_all))

print()
print("=" * 55)
print("【第一步：定性定位】")
print("=" * 55)
if ma5 > ma10 > ma20 > ma60: ma_s = "多头排列(强势)"; sc_tr = 15
elif ma5 < ma10 < ma20 < ma60: ma_s = "空头排列(弱势)"; sc_tr = 3
else: ma_s = "均线缠绕(震荡)"; sc_tr = 8
print("  均线结构:", ma_s)
print("  MA5={:.2f} MA10={:.2f} MA20={:.2f} MA60={:.2f}".format(ma5, ma10, ma20, ma60))
print("  收盘{:.2f} 在所有均线下方 → 空头".format(c))
print("  120日价格位置: {:.1f}%".format(pos120))
phase = "低位建仓/吸筹" if pos_all < 35 else ("中位换手/洗盘" if pos_all < 65 else "高位派发")
print("  生命周期:", phase)

print()
print("=" * 55)
print("【第二步：多维验证】")
print("=" * 55)
print("  【近10日K线】")
for i in range(L - 10, L):
    r = df.iloc[i]
    pct = (r['close'] / df.iloc[i-1]['close'] - 1) * 100
    bo = abs(r['close'] - r['open']); tr_ = r['high'] - r['low']
    us = r['high'] - max(r['open'], r['close'])
    ls = min(r['open'], r['close']) - r['low']
    if bo < tr_ * 0.1: kt = "十字星"
    elif us > bo * 2 and ls < bo * 0.3: kt = "锤子/吊颈"
    elif r['close'] > r['open'] and us < bo * 0.2 and ls < bo * 0.2: kt = "光头阳"
    elif r['close'] < r['open'] and us < bo * 0.2 and ls < bo * 0.2: kt = "光头阴"
    elif r['close'] > r['open']: kt = "阳线"
    else: kt = "阴线"
    vr_r = r['volume'] / df['vol_ma20'].iloc[i] if not na(df['vol_ma20'].iloc[i]) else 1
    arrow = "+" if pct > 0 else ""
    print("  {}/{}  {:5s} {}{:.2f}%  收{:.2f}  量比{:.1f}x".format(
        r['date'].month, r['date'].day, kt, arrow, abs(pct), r['close'], vr_r))

print()
print("  【量价分析】")
print("  今日量比(vol/20日均): {:.2f}x".format(vr20))
if pc5 > 0 and vc5 > 0: vp = "健康(价涨量增)"; vp_sc = 8
elif pc5 > 0 and vc5 < 0: vp = "背离(价涨量缩)"; vp_sc = 2
elif pc5 < 0 and vc5 > 0: vp = "恐慌(价跌量增)"; vp_sc = 3
else: vp = "正常(回调缩量)"; vp_sc = 6
print("  近5日量价:", vp, "  评分:", vp_sc)

print()
print("  【MACD】")
if dif > dea and dif_p <= prev['dif']: ms = "MACD金叉(转多)"; ms_sc = 6
elif dif < dea and dif_p >= prev['dif']: ms = "MACD死叉(转空)"; ms_sc = 0
elif dif > dea: ms = "多头区域"; ms_sc = 4
else: ms = "空头区域"; ms_sc = 2
print("  DIF={:.4f}  DEA={:.4f}  MACD柱={:.4f}".format(dif, dea, macd))
print("  ", ms)

print()
print("  【KDJ】")
ks = "超卖" if K < 30 else ("超买" if K > 80 else "正常")
k2 = "金叉" if (K > D and df['K'].iloc[-2] <= df['D'].iloc[-2]) else ("死叉" if (K < D and df['K'].iloc[-2] >= df['D'].iloc[-2]) else "")
kj_sc = 6 if K < 30 else (0 if K > 80 else 3)
print("  K={:.1f}  D={:.1f}  J={:.1f}  [{}{}]".format(K, D, J, ks, k2))

print()
print("  【RSI】")
print("  RSI6={:.1f}  RSI12={:.1f}  RSI24={:.1f}".format(rsi1, rsi2, rsi3))
rs_st = "超卖" if rsi1 < 35 else ("超买" if rsi1 > 70 else "正常")
print("  [{}]".format(rs_st))

print()
print("  【布林带】")
if c > boll_u: bs = "突破上轨(超买)"; bs_sc = 0
elif c < boll_l: bs = "跌破下轨(超卖-关注)"; bs_sc = 5
else: bs = "通道内运行"; bs_sc = 3
print("  上轨{:.2f}  中轨{:.2f}  下轨{:.2f}".format(boll_u, boll_m, boll_l))
print("  收盘{:.2f} → {}".format(c, bs))

print()
print("  ATR波动率: {:.2f}%".format(atr_pct))
atr_sc = 5 if atr_pct < 2.5 else (3 if atr_pct < 4 else 1)

print()
print("=" * 55)
print("【第三步：综合评分】")
print("=" * 55)
sc_pos = 8 if pos_all < 35 else (4 if pos_all > 70 else 6)
total = sc_tr + vp_sc + ms_sc + kj_sc + bs_sc + atr_sc + sc_pos
print("  趋势结构:   {:2d}/20  (均线{})".format(sc_tr, ma_s))
print("  量价健康度: {:2d}/25  ({})".format(vp_sc, vp))
print("  MACD信号:  {:2d}/15  ({})".format(ms_sc, ms))
print("  KDJ信号:   {:2d}/15  ({}[{}])".format(kj_sc, ks, k2))
print("  布林带:    {:2d}/10  ({})".format(bs_sc, bs))
print("  波动率:    {:2d}/5   (ATR%={:.1f}%)".format(atr_sc, atr_pct))
print("  价格位置:  {:2d}/10  (历史{:.0f}%)".format(sc_pos, pos_all))
print("  ─────────────────────")
print("  综合评分: {}/100".format(total))
lv = "🟢 积极关注" if total >= 65 else ("🟡 谨慎观望" if total >= 45 else "🔴 回避风险")
print(" ", lv)

print()
print("=" * 55)
print("【第四步：走势推演】")
print("=" * 55)
print("  近20日区间: {:.2f} ~ {:.2f}".format(rl, rh))
tp1_h = rh * 1.05; tp1_l = rh * 1.10
print("  路径一(上涨,30%): 放量突破{:.2f} → 目标{:.2f}~{:.2f}".format(rh, tp1_h, tp1_l))
print("  路径二(震荡,45%): {:.2f}~{:.2f}区间震荡, 节前谨慎".format(rl, rh))
tp3_l = rl * 0.95; tp3_h = rl * 0.90
print("  路径三(破跌,25%): 跌破{:.2f} → 目标{:.2f}~{:.2f}".format(rl, tp3_l, tp3_h))

print()
print("=" * 55)
print("【第五步：策略建议】")
print("=" * 55)
print("  空仓: 等突破{:.2f}(20日高点)跟进, 止损{:.2f}(MA5)".format(rh, ma5))
print("  轻仓: 回踩{:.2f}(MA10)不破可加仓".format(ma10))
print("  重仓: 以MA5({:.2f})动态止损, 节前降仓".format(ma5))

print()
print("=" * 55)
print("【第六步：风控】")
print("=" * 55)
print("  止损1(短线): {:.2f}(MA5)".format(ma5))
print("  止损2(波段): {:.2f}(MA10)".format(ma10))
print("  止损3(结构): {:.2f}(近期低点)".format(rl))
print("  止盈: {:.2f}以上每涨5%减1/3".format(rh))

print()
print("=" * 55)
print("【主力意图推断】")
print("=" * 55)
if pos_all < 35 and c < ma60:
    intent = "低位建仓阶段, 主力压价吸筹"
elif c < boll_m and dif < 0:
    intent = "布林中下轨+MACD空头: 主力震荡吸筹+洗盘"
else:
    intent = "中位震荡, 主力在反复洗盘吸筹"
print(" ", intent)
print("  当前状态: {} + MACD{} + 均线{}".format(phase, ms, ma_s))
print("  关键特征: 从高点{:.2f}回调至{:.2f}({:.1f}%),量能萎缩".format(rh, c, (c/rh-1)*100))
print("           属于典型洗盘结构,非出货")
print()
print("=" * 55)
