# A股分析三大核心技能手册
> Jason的A股分析工具箱 | 版本：2026-05-09 | 三套独立并行分析方法

---

## 总览：三种分析体系的关系

```
超短量化（选方向）→ 老股民（验标的）→ 主升浪信号（确认启动点）
    ↓                   ↓                   ↓
情绪/热点/资金      基本面+技术面       四条铁律共振验证
短线机会筛选         全方位诊断          启动点确认
```

| 体系 | 适用场景 | 核心指标 |
|------|---------|---------|
| **老股民个股分析** | 任何个股买前分析、持仓诊断 | 10维验证+100分制 |
| **超短量化分析** | 短线选股、情绪周期、热点轮动 | 涨跌停比+换手率+主力行为 |
| **主升浪信号** | 涨停/大阳线后验证是否进入主升浪 | 四条铁律+概率量化 |

---

## 技能一：老股民个股分析（a-stock-analysis）

### 触发方式
- Jason说"分析XXX"、"用老股民模板分析"
- 需要对个股做完整诊断（买前/持仓/止损决策）

### 报告结构（8步）
```
Step 1 — 定性定位（趋势所处阶段 + 关键依据 + 最大疑点）
Step 2 — 10维技术验证（均线/K线/量价/布林/板块/分价表/RSI/主力行为/北向/筹码）
Step 3 — 综合评分（100分制）
Step 4 — 三路径推演（上涨/震荡/下跌）
Step 5 — 持仓策略（空仓/轻仓/重仓分别说明）
Step 6 — 风控要点（止损线/RSI预警/节前建议）
Step 7 — 基本面验证（7项全列）
Step 8 — 估值水平（5项全列）
```

### Step 7 必须包含7项
1. 证券全称
2. 主营业务
3. 收入结构
4. 行业(三级)
5. 地区
6. 上市日期
7. 题材概念（完整列表）

### Step 8 必须包含5项
1. PE/PB/市值/板块/股价
2. 行业均值对比（PE/PB行业对比）
3. 全部题材概念列表
4. 近30日热点题材Top10
5. 热点匹配结果（⚠️ 无匹配则写"无直接匹配"）

### 数据源优先级
1. Baostock（日K，技术指标）
2. 东财curl API（估值+基本面+题材）
3. Tushare（北向资金，需token）
4. AKShare（备选，不稳定）

### 数据采集核心脚本
```python
import baostock as bs
import pandas as pd
import numpy as np

code = '000600'
prefix = 'sz' if code.startswith(('0','2','3')) else 'sh'
bs_code = f'{prefix}.{code}'

bs.login()
rs = bs.query_history_k_data_plus(bs_code,
    'date,open,high,low,close,volume,amount,pctChg,turn',
    start_date='2026-02-01', end_date='2026-05-08',
    frequency='d', adjustflag='2')
data = []
while rs.next():
    data.append(rs.get_row_data())
df = pd.DataFrame(data, columns=rs.fields)
for col in ['open','high','low','close','volume','amount','pctChg','turn']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)
bs.logout()
```

### 技术指标计算要点
- **rolling()必须加min_periods=1**，否则前N行为NaN导致dropna()清空
- **ATR计算**：
```python
hl = df['high'] - df['low']
hc = abs(df['high'] - df['close'].shift())
lc = abs(df['low'] - df['close'].shift())
tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
df['atr'] = tr.rolling(14, min_periods=1).mean()
df['atr_pct'] = df['atr'] / df['close'] * 100
```

### 东财估值API（filter必须URL编码）
```python
import urllib.parse
FILTER = urllib.parse.quote(f"(TRADE_DATE='2026-05-08')(SECURITY_CODE={code})")
# 注意：SECURITY_CODE字段不加引号！TRADE_DATE必须加引号！
url = ("https://datacenter.eastmoney.com/api/data/v1/get"
       "?reportName=RPT_VALUEANALYSIS_DET"
       "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
       f"&filter={FILTER}&source=WEB&client=WEB")
```

### 筹码分布（CYC成本）
```python
import sys
sys.path.insert(0, '/home/admin/stock_knowledge/scripts')
from chip_distribution import calc_chip_distribution, chip_analysis_text

df_c = df.rename(columns={'turn': 'turnover'})
chip = calc_chip_distribution(df_c, accuracy_factor=150, trading_days=210)
print(chip_analysis_text(chip, code, latest_close))
# 关键：获利>90%=高位风险，<30%=低位机会
```

### 注意事项
- 深市股代码不要用sh.前缀，会导致数据为空
- 东财curl实时行情：`https://push2delay.eastmoney.com/api/qt/stock/get?secid=0.000600&fields=f43,f57,f58,f170`
- 节前（五一/十一）提高路径三概率，提醒空仓
- Tushare stock_basic接口有1次/小时频率限制

---

## 技能二：超短量化分析（a-stock-quant-pipeline）

### 触发方式
- Jason说"筛选短线标的"、"看看最近热点"、"分析情绪周期"
- 需要批量选股、板块轮动分析

### 核心模块
1. **情绪周期四维**：涨跌停比 + 炸板率 + 连板率 + 全市场换手率
2. **_score_turnover()**：量化全市场换手率信号
   - <0.5% = 底部区域
   - 0.5~2% = 正常
   - 2~5% = 活跃
   - 5~10% = 高热
   - >10% = 极度过热
3. **主力行为识别**：建仓型/拉升型/洗盘型/出货型/控盘型

### 主力行为类型定义
| 类型 | 换手率 | 涨幅 | 主力净流入 | 信号 |
|------|--------|------|------------|------|
| 建仓型 | 3~8% | 2~6% | >20% | 积极 |
| 拉升型 | >5% | >5% | >1亿 | 积极 |
| 洗盘型 | >5% | 0~3% | 正负不定 | 观察 |
| 出货型 | >8% | >3% | 负 | 警惕 |
| 控盘型 | 2~4% | <2% | 稳定 | 横盘 |

### 批量筛选示例
```python
# 筛选条件：换手率>3% + 涨幅>3% + 突破均线多头
# 详见 scripts/quick_screen4.py
~/stock_knowledge/venv/bin/python3 scripts/quick_screen4.py
```

### 注意事项
- 换手率字段turn在东财API返回数据中是**小数格式**（0.0247=2.47%），筛选条件用`turn >= 0.01`（≥1%），不是`turn >= 1`
- 均线多头筛选需要至少60天数据（拉足数据避免次新股20日均线显示nan）
- 东财板块资金流API：`https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&fid=f62&fs=m:90+t:2&fields=f12,f14,f2,f3,f62`

---

## 技能三：主升浪信号分析（a-stock-rising-wave）

### 触发方式
- Jason说"分析主升浪信号"、"帮我验证是否进入主升浪"
- 个股出现涨停/大阳线后需要确认是否启动

### 四条铁律

| 铁律 | 内容 | 达标标准 |
|------|------|---------|
| **铁律1** | 高质量大阳线（横盘缩量+量能放大） | 涨幅≥5%（主板）/≥10%（创业板），横盘振幅<15%，量能放大≥1.5倍 |
| **铁律2** | 向上缺口三日不回补 | 大阳日产生跳空缺口，之后3日内不回补 |
| **铁律3** | 阶梯式连阳 | 连续3~4日收阳且每日收盘创新高 |
| **铁律4** | 关键位放量突破 | 突破大阳日前20日最高价，换手率≥1.5倍 |

### 评分体系

| 达标条数（≥7分=达标） | 主升浪成功概率 |
|----------------------|--------------|
| 4条 | 92% |
| 3条 | 86% |
| 2条 | 74% |
| 1条 | 48% |
| 0条 | 20% |

### 使用方法
```python
import sys
sys.path.insert(0, '/home/admin/stock_knowledge/scripts')
from a_stock_rising_wave import RisingWaveAnalyzer

analyzer = RisingWaveAnalyzer()
r = analyzer.analyze('sz.000600', '建投能源', surge_threshold=5.0)
analyzer.print_report(r)
print(f"主升浪成功概率: {r['prob']}%")
```

### 批量筛选
```python
results = analyzer.batch_analyze(
    ['000600', '002715'],
    names=['建投能源', '登云股份'],
    thresholds={'000600': 5.0, '002715': 10.0}
)
for r in results:
    print(f"{r['name']}: {r['prob']}%")
```

### 返回字段
```python
{
    'code': '000600',
    'name': '建投能源',
    'date': '2026-05-08',
    'close': '9.93',
    'scores': {'铁律1_高质量大阳': 7, '铁律2_缺口不补': 10, ...},
    'results': {'铁律1_高质量大阳': '横盘好但未缩量', ...},
    'details': {'铁律1_高质量大阳': {'大阳日':'04-29','涨幅':'6.54%',...}, ...},
    'total': 29,      # 满分40
    'rules_met': 3,   # 达标条数
    'prob': 86        # 成功概率%
}
```

### 陷阱（来自《庄家》书）
1. 铁律3可被庄家对倒造假，单独准确率仅55~60%，必须结合其他铁律
2. **高位出现四条共振 = 主力出货诱多，非启动**
3. 大盘下跌时四条共振可能失败
4. 四条共振后5~8日内未见涨幅>20%加速 = 信号失败

---

## 数据源总览

| 数据类型 | 数据源 | 调用方式 |
|---------|-------|---------|
| 日K线 | Baostock | `bs.query_history_k_data_plus()` |
| 实时行情 | 东财curl | `push2delay.eastmoney.com/api/qt/stock/get` |
| 估值PE/PB | 东财API | `RPT_VALUEANALYSIS_DET` |
| 基本面主营 | 东财API | `RPT_F10_ORG_BASICINFO` |
| 行业均值 | 东财API | `RPT_VALUEINDUSTRY_DET` |
| 题材概念 | 东财curl | `f129字段` |
| 热点板块 | 东财curl | `push2delay.eastmoney.com/api/qt/clist/get` |
| 北向资金 | Tushare | `pro.hk_hold()` |
| 筹码分布 | 本地脚本 | `scripts/chip_distribution.py` |

---

## 文件路径速查

| 文件 | 路径 |
|------|------|
| 主升浪分析脚本 | `/home/admin/stock_knowledge/scripts/a_stock_rising_wave.py` |
| 筹码分布脚本 | `/home/admin/stock_knowledge/scripts/chip_distribution.py` |
| 超短筛选脚本 | `/home/admin/stock_knowledge/scripts/quick_screen4.py` |
| 板块筛选脚本 | `/home/admin/stock_knowledge/scripts/sector_screener.py` |
| 每日主力行为cron | Cron ID: e47a619aeec8（周一~五22:00） |
| 主力行为数据库 | `~/stock_knowledge/data/daily_main_player_analysis.csv` |
| 知识库 | `~/stock_knowledge/knowledge_base/` |
| Python环境 | `/home/admin/stock_knowledge/venv/bin/python3` |

---

## 快速调用模板

### 分析000600全套（三技能组合）
```python
# 1. 超短量化——看方向
# → 运行 scripts/quick_screen4.py 或 sector_screener.py

# 2. 老股民分析——验标的
# → 用 a-stock-analysis 技能输出8步报告

# 3. 主升浪信号——确认启动点
~/stock_knowledge/venv/bin/python3 - << 'EOF'
import sys
sys.path.insert(0, '/home/admin/stock_knowledge/scripts')
from a_stock_rising_wave import RisingWaveAnalyzer
a = RisingWaveAnalyzer()
r = a.analyze('sz.000600', '建投能源', surge_threshold=5.0)
a.print_report(r)
EOF
```

### 批量扫描主升浪信号
```python
~/stock_knowledge/venv/bin/python3 - << 'EOF'
import sys, pandas as pd
sys.path.insert(0, '/home/admin/stock_knowledge/scripts')
from a_stock_rising_wave import RisingWaveAnalyzer

stocks = pd.read_csv('/home/admin/stock_knowledge/data/daily_main_player_analysis.csv')
codes = stocks[stocks['pct_chg'] > 5]['code'].unique()[:20]

a = RisingWaveAnalyzer()
results = a.batch_analyze(codes.tolist())
for r in results:
    print(f"{r['name']}({r['code']}): {r['prob']}% ({r['rules_met']}/4条)")
EOF
```

---

*本手册由纳福整理 | 三套方法论来源：《一本书看透股市庄家》+ 实战积累*
