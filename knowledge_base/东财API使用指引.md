# 东财API使用指引

## 一、估值与基本面（datacenter.eastmoney.com）

### 通用格式
```
https://datacenter.eastmoney.com/api/data/v1/get
?reportName=RPT_XXXXX
&columns=字段1,字段2,...
&pageNumber=1&pageSize=1
&filter=<URL编码的过滤条件>
&source=WEB&client=WEB
```

### ⚠️ filter参数格式规则（必读）
- **日期字段**：必须加引号，如 `TRADE_DATE='2026-05-08'`
- **股票代码字段**：**不加引号**，如 `SECURITY_CODE=600519`
- **数值字段**：不加引号，如 `PE_TTM>10`
- **组合条件**：直接拼接，如 `(TRADE_DATE='2026-05-08')(PE_TTM>0)`
- **必须URL编码**：用 `urllib.parse.quote()` 包裹整个filter字符串

---

## 二、个股估值数据（RPT_VALUEANALYSIS_DET）

### 用途
获取个股实时PE、PB、市值、所属板块

### Python示例
```python
import urllib.parse, subprocess, json

code = '600519'  # 股票代码，不加前缀
date = '2026-05-08'

FILTER = urllib.parse.quote(f"(TRADE_DATE='{date}')(SECURITY_CODE={code})")
url = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_VALUEANALYSIS_DET"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
    f"&pageNumber=1&pageSize=1&filter={FILTER}&source=WEB&client=WEB"
)

r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True)
d = json.loads(r.stdout)
if d.get('result') and d['result'].get('data'):
    row = d['result']['data'][0]
    print(row['SECURITY_NAME_ABBR'])   # 贵州茅台
    print(row['PE_TTM'])               # 市盈率
    print(row['PB_MRQ'])               # 市净率
    print(row['TOTAL_MARKET_CAP'])      # 总市值（单位：元）
    print(row['BOARD_NAME'])            # 所属行业
```

### 常见错误
- SECURITY_CODE加了引号 → 报错9501
- TRADE_DATE没加引号 → 报错9501
- filter未URL编码 → 返回400

---

## 三、个股基本面（RPT_F10_ORG_BASICINFO）

### 用途
获取个股全称、主营、行业三级分类、地区、上市日期

### Python示例
```python
import urllib.parse, subprocess, json

code = '600519'

FILTER = urllib.parse.quote(f"(SECURITY_CODE={code})")
url = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_F10_ORG_BASICINFO"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,ORG_NAME,MAIN_BUSINESS,"
             "INCOME_STRU_NAMENEW,BOARD_NAME_1LEVEL,BOARD_NAME_2LEVEL,BOARD_NAME_3LEVEL,"
             "REGIONBK,GROSS_PROFIT_RATIO,LISTING_DATE"
    f"&pageNumber=1&pageSize=1&filter={FILTER}&source=WEB&client=WEB"
)

r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True)
d = json.loads(r.stdout)
if d.get('result') and d['result'].get('data'):
    co = d['result']['data'][0]
    print(co['SECURITY_NAME_ABBR'])   # 简称
    print(co['ORG_NAME'])             # 全称
    print(co['MAIN_BUSINESS'])        # 主营业务
    print(co['INCOME_STRU_NAMENEW'])  # 收入结构
    print(co['BOARD_NAME_1LEVEL'])    # 行业一级
    print(co['BOARD_NAME_2LEVEL'])    # 行业二级
    print(co['BOARD_NAME_3LEVEL'])    # 行业三级
    print(co['REGIONBK'])             # 地区
    print(co['LISTING_DATE'])         # 上市日期
```

---

## 四、行业估值均值（RPT_VALUEINDUSTRY_DET）

### 用途
获取行业PE/PB均值，用于个股估值对比

### Python示例
```python
import urllib.parse, subprocess, json

sector = '电力'  # 行业名称，需与RPT_VALUEANALYSIS_DET返回的BOARD_NAME一致
date = '2026-05-08'

FILTER = urllib.parse.quote(f"(TRADE_DATE='{date}')(BOARD_NAME='{sector}')")
url = (
    "https://datacenter.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_VALUEINDUSTRY_DET"
    "&columns=BOARD_NAME,PE_TTM,PB_MRQ,NUM,LOSS_COUNT"
    f"&pageNumber=1&pageSize=5&sortColumns=PE_TTM&sortTypes=1&filter={FILTER}&source=WEB&client=WEB"
)

r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True)
d = json.loads(r.stdout)
if d.get('result') and d['result'].get('data'):
    for row in d['result']['data']:
        print(f"行业:{row['BOARD_NAME']} PE均值={row['PE_TTM']:.1f} PB={row['PB_MRQ']:.2f} 个股数={row['NUM']}")
```

---

## 五、实时行情curl（push2delay.eastmoney.com）

### 用途
获取个股实时价格、涨跌幅、成交量等

### secid格式（必读）
- **沪市**：前缀`1.`，如 `1.600519`
- **深市**：前缀`0.`，如 `0.000600`

### 字段说明
| 字段 | 说明 |
|------|------|
| f43 | 现价（原始值÷100） |
| f57 | 代码 |
| f58 | 名称 |
| f169 | 涨跌额（原始值÷100） |
| f170 | 涨跌幅（原始值÷100） |
| f44 | 最高 |
| f45 | 最低 |
| f46 | 今开 |
| f60 | 昨收 |
| f47 | 成交量（手） |
| f48 | 成交额（原始值÷100） |
| f129 | 题材概念（逗号分隔） |

### Python示例
```python
import subprocess, json

secid = '0.000600'  # 深市建投能源
url = (
    f"https://push2delay.eastmoney.com/api/qt/stock/get"
    f"?secid={secid}&fields=f43,f57,f58,f169,f170,f44,f45,f46,f60,f47,f48,f129"
    f"&ut=fa5fd1943c7b386f172d6893dbfba10b"
)

r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"], capture_output=True, text=True)
d = json.loads(r.stdout)['data']
print(f"{d['f58']}({d['f57']}) 现价:{d['f43']/100:.2f} 涨跌:{d['f170']/100:+.2f}%")
print(f"题材:{d.get('f129','')}")
```

### 一行Shell命令
```bash
curl -s "https://push2delay.eastmoney.com/api/qt/stock/get?secid=0.000600&fields=f43,f57,f58,f169,f170&ut=fa5fd1943c7b386f172d6893dbfba10b" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys,json; d=json.load(sys.stdin)['data']
print(f\"{d['f58']}({d['f57']}) 现价:{d['f43']/100:.2f} 涨跌:{d['f170']/100:+.2f}%\")"
```

---

## 六、板块资金流（push2.eastmoney.com）

### 用途
获取行业/概念板块主力净流入排名

### 参数说明
| 参数 | 说明 |
|------|------|
| pn | 页码 |
| pz | 每页数量 |
| po=1 | 降序 |
| fid=f62 | 按主力净流入排序 |
| fs=m:90+t:2 | 行业板块（t:2=行业，t:3=概念） |

### 一行Shell命令（行业资金流Top10）
```bash
curl -s "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1&fid=f62&fs=m:90+t:2&fields=f12,f14,f2,f3,f62&ut=bd1d9ddb04089700cf9c27f6f7426281" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for r in d['data']['diff']:
    print(f\"{r['f14']} 净流入:{r['f62']/10000:.0f}万 涨跌:{r['f3']/100:+.2f}%\")"
```

### 一行Shell命令（概念资金流Top10）
```bash
curl -s "https://push2delay.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1&fid=f62&fs=m:90+t:3&fields=f12,f14,f2,f3,f62&ut=bd1d9ddb04089700cf9c27f6f7426281" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for r in d['data']['diff']:
    print(f\"{r['f14']} 净流入:{r['f62']/10000:.0f}万\")"
```

---

## 七、热点板块排名（近期涨幅最大的板块）

### 一行Shell命令
```bash
curl -s "https://push2delay.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=1&np=1&fid=f3&fs=m:90+t:3&fields=f12,f14,f2,f3,f62&ut=bd1d9ddb04089700cf9c27f6f7426281" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for r in d['data']['diff']:
    print(f\"{r['f14']} 涨幅:{r['f3']/100:+.2f}% 主力净流入:{r['f62']/10000:.0f}万\")"
```

---

## 八、常见陷阱汇总

| 陷阱 | 正确做法 |
|------|---------|
| SECURITY_CODE加了引号如 `SECURITY_CODE='600519'` | 不加引号：`SECURITY_CODE=600519` |
| TRADE_DATE没加引号 | 必须加：`TRADE_DATE='2026-05-08'` |
| filter未URL编码 | 用 `urllib.parse.quote(f"(TRADE_DATE='{date}')(PE_TTM>0)")` |
| 深市股票secid写成`1.000600` | 深市用`0.`前缀：`0.000600` |
| 沪市股票secid写成`0.600519` | 沪市用`1.`前缀：`1.600519` |
| curl返回空 | 加 `-H "User-Agent: Mozilla/5.0"` 模拟浏览器 |

---

## 九、辅助函数（Python封装）

```python
import subprocess, json, urllib.parse

def curl_json(url):
    """通用的curl+JSON解析"""
    r = subprocess.run(
        ["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
        capture_output=True, text=True, timeout=20
    )
    try:
        return json.loads(r.stdout)
    except:
        return {}

def get_valuation(code, date):
    """获取个股估值"""
    FILTER = urllib.parse.quote(f"(TRADE_DATE='{date}')(SECURITY_CODE={code})")
    url = (
        "https://datacenter.eastmoney.com/api/data/v1/get"
        "?reportName=RPT_VALUEANALYSIS_DET"
        "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
        f"&pageNumber=1&pageSize=1&filter={FILTER}&source=WEB&client=WEB"
    )
    d = curl_json(url)
    if d.get('result') and d['result'].get('data'):
        r = d['result']['data'][0]
        return {
            'name': r['SECURITY_NAME_ABBR'],
            'pe': r.get('PE_TTM', 0),
            'pb': r.get('PB_MRQ', 0),
            'mkt': r.get('TOTAL_MARKET_CAP', 0) / 1e8,
            'sector': r.get('BOARD_NAME', '')
        }
    return None

def get_realtime(code, exchange='sh'):
    """获取实时行情"""
    # exchange: 'sh'=1.前缀, 'sz'=0.前缀
    secid = f"1.{code}" if exchange == 'sh' else f"0.{code}"
    url = (
        f"https://push2delay.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}&fields=f43,f57,f58,f169,f170,f129"
        f"&ut=fa5fd1943c7b386f172d6893dbfba10b"
    )
    d = curl_json(url)
    if d.get('data'):
        r = d['data']
        return {
            'name': r['f58'],
            'code': r['f57'],
            'price': r['f43'] / 100,
            'pct': r['f170'] / 100,
            'concepts': r.get('f129', '')
        }
    return None
```

---

## 十、股票代码判断规则

```python
def get_exchange(code):
    """
    判断股票市场前缀
    6开头 -> 沪市 -> sh. + 1.
    0/2/3开头 -> 深市 -> sz. + 0.
    """
    if code.startswith('6'):
        return 'sh', f'sh.{code}', f'1.{code}'
    else:  # 0, 2, 3开头
        return 'sz', f'sz.{code}', f'0.{code}'
```

---

*整理自实战积累 | 东财API无需token，直接可用*
