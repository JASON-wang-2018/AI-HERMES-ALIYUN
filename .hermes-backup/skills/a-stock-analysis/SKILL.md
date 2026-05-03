---
name: a-stock-analysis
description: A股个股结构化技术分析，输出老股民分析模板报告（8步：定性定位→9维验证→100分评分→3路径推演→持仓策略→风控→基本面验证→估值水平）
trigger: "当Jason要求分析A股个股（“分析XXX”、“用老股民分析模板分析”）或发来股票数据文件（.xls/.csv）时，加载本技能"
category: productivity
---

# a-stock-analysis

## 知识库
核心框架：`~/stock_knowledge/knowledge_base/A股实战分析统一框架.md`（老股民分析模板v2.0）

## 执行步骤

### Step 1: 数据采集
优先使用 **Baostock + 东财估值API组合**，AKShare作为备选。

**⚠️ 股票代码前缀（必读）：**
- 沪市（6开头）：Baostock用 `sh.XXXXXX`
- 深市（0/2/3开头）：Baostock用 `sz.XXXXXX`
- **勿写死`sh.`，否则深市股票数据为空！** 自动判断：
  ```python
  code = '002457'
  prefix = 'sz' if code.startswith(('0','2','3')) else 'sh'
  bs_code = f'{prefix}.{code}'
  ```

**重要：先采集近15日详细K线（用于第一步定性定位）**
```python
# 近15日详细K线——支撑量价背离/K线形态/主力行为判断
bs_code = f"{'sz' if code.startswith(('0','2','3')) else 'sh'}.{code}"
rs2 = bs.query_history_k_data_plus(bs_code,
    'date,open,high,low,close,volume,amount,pctChg',
    start_date='2026-04-10', end_date='2026-04-28',
    frequency='d', adjustflag='2')
detail = []
while rs2.next():
    detail.append(rs2.get_row_data())
df_det = pd.DataFrame(detail, columns=rs2.fields)
for col in ['open','high','low','close','volume','amount','pctChg']:
    df_det[col] = pd.to_numeric(df_det[col], errors='coerce')
# 打印格式（供Step1定性定位分析）：
for _, r in df_det.iterrows():
    print(f"{r['date']}  开:{r['open']:.2f} 高:{r['high']:.2f} 低:{r['low']:.2f} 收:{r['close']:.2f} {r['pctChg']:+.2f}% 量:{r['volume']/1e4:.0f}万")
```

采集完成后，**先分析近15日详细数据**（目测量价关系/K线形态/主力异动），再执行完整指标计算。

**重要限制：**
- Tushare `stock_basic` 接口频率限制（1次/小时），避免重复调用
- AKShare 容易 `RemoteDisconnected`，需要加 try/except
- Baostock 日期格式必须是 `YYYY-MM-DD`
- **rolling()指标必须加`min_periods=1`**，否则前N行全是NaN会导致后续`dropna()`清空整表

#### 采集脚本（推荐：Baostock日K + 东财估值API）
```bash
cd ~/stock_knowledge && source venv/bin/activate
python3 - << 'PYEOF'
import pandas as pd
import baostock as bs
import numpy as np
import subprocess, json, urllib.parse

code = '002457'  # ← 改这里
prefix = 'sz' if code.startswith(('0','2','3')) else 'sh'

bs.login()
rs = bs.query_history_k_data_plus(f'{prefix}.{code}',
    'date,open,high,low,close,volume,amount,pctChg',
    start_date='2026-02-01', end_date='2026-04-28',
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

# === 技术指标（rolling加min_periods=1防止dropna清空）===
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
# ATR（⚠️ 必须计算，a-stock-analysis旧版漏算了）
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

# === 东财估值API（⚠️ filter必须URL编码）===
FILTER = urllib.parse.quote(f"(TRADE_DATE='2026-04-28')(SECURITY_CODE='{code}')")
url_gz = ("https://datacenter.eastmoney.com/api/data/v1/get"
          "?reportName=RPT_VALUEANALYSIS_DET"
          "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
          "&pageNumber=1&pageSize=1&filter=" + FILTER + "&source=WEB&client=WEB")
r = subprocess.run(["curl","-s",url_gz,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True)
try:
    gd = json.loads(r.stdout)
    if gd.get('result') and gd['result'].get('data'):
        gr = gd['result']['data'][0]
        name, pe, pb, mkt, sector = gr['SECURITY_NAME_ABBR'], gr.get('PE_TTM',0), gr.get('PB_MRQ',0), gr.get('TOTAL_MARKET_CAP',0)/1e8, gr.get('BOARD_NAME','')
    else:
        name, pe, pb, mkt, sector = code, 0, 0, 0, ''
except:
    name, pe, pb, mkt, sector = code, 0, 0, 0, ''

print(f"\n=== {name}({code}) 技术数据 ===")
print(f"估值: PE={pe:.1f} PB={pb:.2f} 市值={mkt:.0f}亿 板块={sector}")
print(f"收盘:{latest['close']:.2f} 涨跌:{latest['pctChg']:+.2f}% ATR%:{latest['atr_pct']:.2f}%")
print(f"MA5={latest['ma5']:.3f} MA10={latest['ma10']:.3f} MA20={latest['ma20']:.3f} MA60={latest['ma60']:.3f}")
print(f"MACD={latest['macd']:.4f}({'红柱' if latest['macd']>0 else '绿柱'}) K={latest['k']:.2f} D={latest['d']:.2f} J={latest['j']:.2f}")
print(f"RSI6={latest['rsi6']:.1f} RSI12={latest['rsi12']:.1f} RSI24={latest['rsi24']:.1f}")
print(f"BOLL:{latest['boll_l']:.3f}/{latest['boll_m']:.3f}/{latest['boll_u']:.3f} 位置:{pos_in_boll:.1%}")
print(f"量比:{latest['vol_ratio']:.2f} 20日位置:{pos_in_20d:.1%}")
print(f"量价背离={divergence_signal} 缩量={volume_compressed} 爆量={vol_breakout} 支撑={support_signal}")
PYEOF
```

#### 东财估值API（批量扫描低估值个股）

**接口**：`https://datacenter.eastmoney.com/api/data/v1/get`
**报表名**：`RPT_VALUEANALYSIS_DET`（个股）；`RPT_VALUEINDUSTRY_DET`（行业）
**⚠️ filter参数必须URL编码**：`urllib.parse.quote("(TRADE_DATE='2026-04-28')(PE_TTM>0)(PE_TTM<20)")`

```python
import subprocess, json, urllib.parse

# 低PE个股（PE 5-20，盈利股）
FILTER = urllib.parse.quote("(TRADE_DATE='2026-04-28')(PE_TTM>5)(PE_TTM<20)(PB_MRQ<3)(CHANGE_RATE>-8)")
url = ("https://datacenter.eastmoney.com/api/data/v1/get"
       "?reportName=RPT_VALUEANALYSIS_DET"
       "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,CHANGE_RATE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
       "&pageNumber=1&pageSize=500&sortColumns=PE_TTM&sortTypes=1"
       "&filter=" + FILTER + "&source=WEB&client=WEB")
r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True)
d = json.loads(r.stdout)
df = pd.DataFrame(d['result']['data'])
print(f"低PE个股: {len(df)} 只")
```

#### 东财实时行情API（curl）
```bash
# secid格式：沪市=1.XXXXXX  深市=0.XXXXXX
# 字段：f43=现价 f57=代码 f58=名称 f170=涨跌幅 f44=最高 f45=最低 f46=今开 f60=昨收 f47=成交量 f48=成交额（÷100还原）
curl -s "https://push2delay.eastmoney.com/api/qt/stock/get?secid=0.002457&fields=f43,f57,f58,f169,f170,f44,f45,f46,f60,f47,f48" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys,json; d=json.load(sys.stdin)['data']
print(f\"{d['f58']}({d['f57']}) 现价:{d['f43']/100:.2f} 涨跌:{d['f170']/100:+.2f}%\")"
```

#### 东财板块资金流（curl）
```bash
# 行业板块资金流 top10（f62=主力净流入，万元）
curl -s "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f2,f3,f62&_=1" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for r in d['data']['diff'][:10]: print(f\"{r['f14']} 净流入:{r['f62']/10000:.0f}万\")"
```

#### AKShare 备选（需加 try/except）
```bash
cd ~/stock_knowledge && source venv/bin/activate
python3 - << 'EOF'
import akshare as ak, pandas as pd
try:
    df = ak.stock_zh_a_hist(symbol='002457', period='daily', start_date='20260401', end_date='20260428', adjust='qfq')
    df.columns = [c.lower() for c in df.columns]
    df['date'] = pd.to_datetime(df['日期'])
    df = df.sort_values('date').reset_index(drop=True)
    print("AKShare OK:", len(df), "条")
except Exception as e:
    print("AKShare失败:", str(e)[:60])
EOF
```

### Step 2: 按老股民分析模板输出报告
**⚠️ 报告内容完整性要求（必须严格遵守，不得遗漏任何数据）：**

**分析维度已升级为10个（新增第⑩维度：筹码分布）**

**Step 7 必须包含全部7项：**
1. 全称
2. 主营（主营业务描述）
3. 收入结构
4. 行业(三级)
5. 地区
6. 上市日期
7. 题材概念（完整列表）

**Step 8 必须包含全部5项：**
1. PE/PB/市值/板块/股价
2. 行业均值对比（行业PE/PB对比）
3. 全部题材概念列表
4. 近30日热点题材Top10
5. 热点匹配结果（有就列出匹配项，无则写"⚠️ 无直接匹配"）

严格按照以下8步结构输出：

```
## Step 1 · 定性定位
【阶段定位】：...
【关键依据】：3条最有力证据
【最大疑点】：1个矛盾信号

## Step 2 · 10维度技术验证
| 维度 | 状态 | 详情 |
|------|------|------|
（10个维度全部列出，数据+信号+评分）

### ⑩筹码分布（CYC成本）数据采集
在Step 1数据采集后，增加筹码分布计算：

```python
import sys
sys.path.insert(0, '~/stock_knowledge/scripts')
from chip_distribution import calc_chip_distribution, chip_analysis_text
import pandas as pd

# 筹码分布需要含换手率数据，用Baostock的turn字段
# df须含列：date, open, high, low, close, turnover（换手率%）
# 示例：用Baostock获取（含turn字段）
import baostock as bs
bs.login()
rs = bs.query_history_k_data_plus(bs_code,
    'date,open,high,low,close,volume,amount,pctChg,turn',  # ← 注意加了turn
    start_date='2024-07-01', end_date='2026-04-30',
    frequency='d', adjustflag='2')
# 同样处理数据后：
df = df.rename(columns={'turn': 'turnover'})
chip = calc_chip_distribution(df, accuracy_factor=150, trading_days=210)
print(chip_analysis_text(chip, code, latest['close']))
```

**关键输出字段：**
- `chip.benefit_part`：获利比例（>90%=高位风险，<30%=低位机会）
- `chip.avg_cost`：平均成本（当前价低于成本=低估）
- `chip.percent_chips['90']['priceRange']`：90%筹码集中区间
- `chip.percent_chips['70']['priceRange']`：70%筹码集中区间（核心成本区）
- 70%区间下沿 = 强支撑；上沿 = 短期压力

## Step 3 · 综合评分：X/100
（所有触发信号列表 + 评分结构拆解）

## Step 4 · 3条走势路径推演
| 路径 | 概率 | 描述 | 关键价位 |
（3条路径全部列出）

## Step 5 · 持仓策略
| 情形 | 操作 |
（空仓/已持仓/节后分别说明）

## Step 6 · 风控要点
（止损线/RSI超买/节前建议全部列出）

## Step 7 · 基本面验证（7项全列）
1. 全称：...
2. 主营：...
3. 收入结构：...
4. 行业(三级)：...
5. 地区：...
6. 上市日期：...
7. 题材概念：...

## Step 8 · 估值水平（5项全列）
1. 估值：PE=... PB=... 市值=...亿 板块=... 股价=...
2. 行业均值对比：...
3. 题材概念(X个)：[完整列表]
4. 近30日热点题材Top10：...
5. 热点匹配：...

## 综合研判
一段话：技术面+基本面+核心矛盾+建议
```

### 主力行为识别（维度8）——关键数据采集
在数据采集脚本中增加以下主力行为指标：

```python
# === 主力行为识别 ===
# 1. 量价背离（吸筹信号）
recent_5 = df_clean.tail(5)
recent_10 = df_clean.tail(10)
price_trend = recent_5['close'].iloc[-1] - recent_5['close'].iloc[0]
vol_trend = recent_5['volume'].iloc[-1] - recent_5['volume'].iloc[0]
# 上涨缩量=主力控盘；下跌放量=主力吸筹
divergence_signal = (price_trend > 0 and vol_trend < 0) or (price_trend < 0 and vol_trend > 0)

# 2. 振幅压缩（吸筹/洗盘）
recent_20_amp = (recent_20['high'] - recent_20['low']) / recent_20['low'] * 100
avg_amp_20 = recent_20_amp.mean()
amp_compressed = avg_amp_20 < 3.0  # 振幅持续低于3%可能是吸筹

# 3. 缩量整理（主力控盘）
vol_recent_avg = recent_5['volume'].mean()
vol_prev_avg = df_clean.tail(20).iloc[:-5]['volume'].mean()
volume_compressed = vol_recent_avg < vol_prev_avg * 0.6  # 缩量60%以上

# 4. 爆量拉升（拉升/建仓）
vol_breakout = latest['vol_ratio'] > 1.5 and latest['pctChg'] > 3.0

# 5. 压单/托单识别（庄家痕迹）
# 需用分时数据，此处用日K振幅+上下影线估算
high_upper_shadow = latest['high'] - max(latest['open'], latest['close'])
low_lower_shadow = min(latest['open'], latest['close']) - latest['low']
body = abs(latest['close'] - latest['open'])
# 上影线长=压盘；下影线长=托单
pressure_signal = high_upper_shadow > body * 1.5  # 压盘痕迹
support_signal = low_lower_shadow > body * 1.5    # 托单痕迹

# 6. 主力阶段判断
if vol_breakout and latest['pctChg'] > 5:
    main_stage = '拉升'
elif divergence_signal and volume_compressed:
    main_stage = '吸筹/洗盘'
elif volume_compressed and amp_compressed:
    main_stage = '控盘/整理'
elif latest['vol_ratio'] > 2.0:
    main_stage = '主力异动'
else:
    main_stage = '无明显主力痕迹'

print(f"DIVERGENCE:{divergence_signal}")
print(f"AMP_COMPRESSED:{amp_compressed}")
print(f"VOL_COMPRESSED:{volume_compressed}")
print(f"VOL_BREAKOUT:{vol_breakout}")
print(f"PRESSURE:{pressure_signal}")
print(f"SUPPORT:{support_signal}")
print(f"MAIN_STAGE:{main_stage}")
```

## 输出语言
全程中文，简洁有力，数据说话。

## 注意事项
- 若Jason发来.xls文件，**先判断文件格式**：通达信导出的.xls通常是GBK编码的制表符分隔文本（不是Excel二进制），直接read_excel会失败。正确方式：
  ```python
  # 方法1（推荐）：制表符分隔文本
  df = pd.read_csv('xxx.xls', sep='\s+', encoding='gbk', header=1)
  # 方法2：engine指定
  df = pd.read_excel('xxx.xls', engine='xlrd')  # 也会失败，需手动指定engine
  ```
- 通达信XLS列名因版本而异，**不要依赖固定的列索引映射**。实际用 `df.columns.tolist()` 确认。实测881394证券板块.xls列名：`['时间','开盘','最高','最低','收盘','成交量','MA58.MA5','MA58.MA10','MA58.MA20','MA58.MA60','MA58.MA120','VOL88.VOLUME','VOL88.VOL5','VOL88.VOL10','VOL88.VOL120','VOL88.VOL60','VOL88.~比例','RSI8.RSI1','RSI8.RSI2','RSI8.RSI3']`
- 注意清理：文件末尾可能有"#数据来源:通达信"等说明行，用 `df[df['时间'].str.match(r'\d{4}/\d{2}/\d{2}')]` 过滤
- TDX板块数据（如881394证券）的MA和RSI列名前缀带指标ID（如MA58.、RSI8.），成交量列可能原始值就是手为单位，无需/100还原
- 节前（五一/十一假期前）提高路径三(回调)概率，提醒轻仓/空仓
- 东财curl实时API可绕过浏览器限制（容器内Chrome无法启动，但curl可用）；优先顺序：Baostock日K > 东财curl实时 > Tushare > AKShare
- AKShare网络不稳定（RemoteDisconnected高频），需加try/except
- Baostock日期格式必须是YYYY-MM-DD，adjustflag='2'为前复权
- Tushare stock_basic接口有1次/小时的频率限制，避免在短时间内重复调用
- **rolling()指标必须加`min_periods=1`**——不加则前N行为NaN，后续`dropna()`会清空整表导致`IndexError`
- 股票代码格式：Baostock用`sh.XXXXXX`（沪市）或`sz.XXXXXX`（深市）；**深市股不能用sh.前缀**
- 9维框架（已去除MACD/KDJ滞后指标）：均线/K线/量价/布林/板块/分价表/RSI/主力行为/北向资金
- **新增第⑩维度**：筹码分布（CYC成本），位于 `scripts/chip_distribution.py`，Baostock的`turn`字段提供换手率数据，210日计算窗口
- **飞书推送模块**：`scripts/feishu_sender.py`，支持签名认证、长消息分片（按###/---/段落分割）、卡片+文本双模式，从环境变量`FEISHU_WEBHOOK_URL`读取
- **情绪周期升级**：整合涨跌停比+炸板率+连板+全市场换手率四维，`_score_turnover()`评分函数量化换手率信号（<0.5%底部/0.5~2%正常/2~5%活跃/5~10%高热/>10%极度过热）
- 分价表数据获取：新浪/东财接口，akshare `stock_zh_a_hist`成交明细备用
- **东财估值API（datacenter.eastmoney.com）：filter参数必须URL编码**，`urllib.parse.quote("(TRADE_DATE='2026-04-28')(PE_TTM>0)")`，否则返回400
- **东财板块资金流API**：可省略`cb=jQuery&_=1`参数，直接返回JSON（不包裹jQuery回调）
- **atr_pct字段**：需手动计算（`df['atr']/df['close']*100`），东财原始数据不含此字段
- **RPT_VALUEANALYSIS_DET 的 SECURITY_CODE 字段filter格式**：`SECURITY_CODE=002457`（**不加引号**），加引号会报9501错误；TRADE_DATE字段则必须加引号：`TRADE_DATE='2026-04-28'`

#### 采集脚本——基本面+题材+热点匹配（Step 7 & Step 8 专用）

```python
import subprocess, json, urllib.parse

code = '002457'  # ← 改这里
DATE = '2026-04-28'

def curl_json(url):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                       capture_output=True, text=True, timeout=20)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# ════ Step 7 基本面：主营 + 行业 ════
# RPT_F10_ORG_BASICINFO：主营/实际控制人/注册信息
FILTER_F10 = urllib.parse.quote("(SECURITY_CODE=" + code + ")")
url_f10 = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_F10_ORG_BASICINFO"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,ORG_NAME,MAIN_BUSINESS,"
             "INCOME_STRU_NAMENEW,BOARD_NAME_1LEVEL,BOARD_NAME_2LEVEL,BOARD_NAME_3LEVEL,"
             "REGIONBK,GROSS_PROFIT_RATIO,LISTING_DATE"
    "&pageNumber=1&pageSize=1&filter=" + FILTER_F10 + "&source=WEB&client=WEB"
)
r_f10 = curl_json(url_f10)
if r_f10.get('result') and r_f10['result'].get('data'):
    co = r_f10['result']['data'][0]
    print(f"  简称: {co['SECURITY_NAME_ABBR']}")
    print(f"  全称: {co['ORG_NAME']}")
    print(f"  主营: {co['MAIN_BUSINESS']}")
    print(f"  收入结构: {co['INCOME_STRU_NAMENEW']}")
    print(f"  行业(三级): {co['BOARD_NAME_1LEVEL']}-{co['BOARD_NAME_2LEVEL']}-{co['BOARD_NAME_3LEVEL']}")
    print(f"  地区: {co['REGIONBK']} 上市日期: {co['LISTING_DATE']}")

# ════ Step 8 估值 ════
# RPT_VALUEANALYSIS_DET（⚠️ SECURITY_CODE不加引号！）
FILTER_V = urllib.parse.quote("(TRADE_DATE='" + DATE + "')(SECURITY_CODE=" + code + ")")
url_val = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_VALUEANALYSIS_DET"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
    "&pageNumber=1&pageSize=1&filter=" + FILTER_V + "&source=WEB&client=WEB"
)
r_val = curl_json(url_val)
if r_val.get('result') and r_val['result'].get('data'):
    vc = r_val['result']['data'][0]
    pe = vc.get('PE_TTM', 0)
    pb = vc.get('PB_MRQ', 0)
    mkt = vc.get('TOTAL_MARKET_CAP', 0) / 1e8
    sector = vc.get('BOARD_NAME', '')
    price = vc.get('CLOSE_PRICE', 0)
    print(f"\n  估值: PE={pe:.1f} PB={pb:.2f} 市值={mkt:.0f}亿 板块={sector} 股价={price}")

# RPT_VALUEINDUSTRY_DET：行业PE/PB均值对比
FILTER_IND = urllib.parse.quote("(TRADE_DATE='" + DATE + "')(BOARD_NAME='" + sector + "')")
url_ind = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_VALUEINDUSTRY_DET"
    "&columns=BOARD_NAME,PE_TTM,PB_MRQ,NUM,LOSS_COUNT"
    "&pageNumber=1&pageSize=5&sortColumns=PE_TTM&sortTypes=1"
    "&filter=" + FILTER_IND + "&source=WEB&client=WEB"
)
r_ind = curl_json(url_ind)
if r_ind.get('result') and r_ind['result'].get('data'):
    for ind in r_ind['result']['data']:
        print(f"  行业: {ind['BOARD_NAME']} PE均值={ind['PE_TTM']:.1f} PB={ind['PB_MRQ']:.2f} 个股数={ind['NUM']} 亏损={ind['LOSS_COUNT']}家")

# ════ Step 8 题材概念 ════
# push2delay f129字段：个股所属题材概念
secid = ("0." + code) if code.startswith(('0','2','3')) else ("1." + code)
url_concept = (
    "https://push2delay.eastmoney.com/api/qt/stock/get"
    "?secid=" + secid + "&fields=f58,f57,f129"
    "&ut=fa5fd1943c7b386f172d6893dbfba10b"
)
r_con = curl_json(url_concept)
concepts = []
if r_con.get('data') and r_con['data'].get('f129'):
    concepts = [c.strip() for c in r_con['data']['f129'].split(',') if c.strip()]
    print(f"\n  题材概念({len(concepts)}个): {concepts}")

# ════ Step 8 近30日热点题材匹配 ════
# fs=m:90+t:3 = 概念板块，按涨幅排序取Top30
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
    print(f"\n  近30日热点题材 Top15:")
    for i, h in enumerate(hot_sectors[:15], 1):
        print(f"    {i:2d}. {h['name']:<12} {h['pct_chg']:>+6.2f}%")

# 题材匹配分析
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
        print(f"    ✓ {m['concept']} → {m['hot']} {m['pct']:+.2f}% 主力:{m['mf']:+.0f}万")
else:
    print(f"    ⚠️ 无直接匹配的30日热点题材")
```
