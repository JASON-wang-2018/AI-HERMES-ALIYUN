import baostock as bs
import pandas as pd
import subprocess
import json
import urllib.parse

def curl_json(url):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {}

lg = bs.login()

# 半导体相关概念股 - 用Baostock获取K线数据
semi_stocks = [
    ('sz.002371', '北方华创'),
    ('sh.688981', '中芯国际'),
    ('sz.002459', '晶澳科技'),
    ('sz.002236', '大立光'),
    ('sh.600584', '长电科技'),
    ('sz.002185', '华天科技'),
    ('sz.600460', '士兰微'),
    ('sh.688396', '华润微'),
    ('sz.002484', '江海股份'),
    ('sh.603986', '兆易创新'),
    ('sz.300666', '江苏租赁'),
    ('sz.002049', '紫光国微'),
    ('sh.688008', '澜起科技'),
    ('sz.300408', '三环集团'),
    ('sh.688012', '中微公司'),
    ('sz.300782', '卓胜微'),
    ('sh.688256', '寒武纪'),
    ('sz.002156', '通富微电'),
    ('sh.600745', '闻泰科技'),
    ('sz.300623', '捷捷微电'),
    ('sz.300496', '中科创达'),
    ('sh.688521', '芯原股份'),
    ('sz.002405', '四维图新'),
    ('sh.688099', '晶晨股份'),
    ('sz.300474', '景嘉微'),
    ('sh.688220', '翱捷科技'),
    ('sz.002180', '纳思达'),
    ('sh.688981', '中芯国际'),
    ('sz.300346', '南大光电'),
    ('sh.688396', '华润微'),
    ('sz.002371', '北方华创'),
    ('sh.688111', '金山办公'),
    ('sz.300223', '北京君正'),
    ('sh.688981', '中芯国际'),
    ('sz.600745', '闻泰科技'),
    ('sh.688981', '中芯国际'),
    ('sz.300666', '江苏吴中'),
    ('sh.688981', '中芯国际'),
]

# 去重
seen = set()
unique_stocks = []
for code, name in semi_stocks:
    if code not in seen:
        seen.add(code)
        unique_stocks.append((code, name))

print(f"待查询: {len(unique_stocks)} 只股票")

results = []
for code, name in unique_stocks:
    rs = bs.query_history_k_data_plus(
        code,
        "date,code,open,high,low,close,volume,amount,turn",
        start_date='2026-04-01',
        end_date='2026-05-06',
        frequency="d"
    )
    data_list = []
    while rs.error_code == '0' and rs.next():
        data_list.append(rs.get_row_data())
    if data_list:
        df = pd.DataFrame(data_list, columns=rs.fields)
        if len(df) > 0:
            latest = df.iloc[-1]
            close = float(latest['close']) if latest['close'] else 0
            turn = float(latest['turn']) if latest['turn'] else 0
            results.append({
                'code': code,
                'name': name,
                'close': close,
                'turn': turn,
                'df': df,
            })

bs.logout()

# 按股价筛选 <=20元
print("\n=== 半导体产业链个股（股价<=20元）===")
print(f"{'名称':<12} {'代码':<12} {'最新价':<10} {'换手%':<8}")
print("-" * 45)
for r in sorted(results, key=lambda x: x['close']):
    if r['close'] > 0 and r['close'] <= 20:
        print(f"{r['name']:<12} {r['code']:<12} {r['close']:<10.2f} {r['turn']:<8.2f}")

# 获取估值数据
print("\n\n=== 获取估值数据 ===")
DATE = '2026-05-06'

def get_valuation(code_raw):
    code_only = code_raw.split('.')[1]
    FILTER = urllib.parse.quote(f"(TRADE_DATE='{DATE}')(SECURITY_CODE={code_only})")
    url = (
        "https://datacenter.eastmoney.com/api/data/v1/get"
        "?reportName=RPT_VALUEANALYSIS_DET"
        "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
        f"&pageNumber=1&pageSize=1&filter={FILTER}&source=WEB&client=WEB"
    )
    r = curl_json(url)
    if r.get('result') and r.get('result').get('data'):
        return r['result']['data'][0]
    return None

# 筛选<=20元的股票详细估值
print(f"\n{'名称':<10} {'最新价':<8} {'PE':<8} {'PB':<6} {'市值(亿)':<10} {'板块'}")
print("-" * 70)
stock_20 = [r for r in results if 0 < r['close'] <= 20]
for r in stock_20[:30]:  # 最多30只
    code_raw = r['code']
    val = get_valuation(code_raw)
    if val:
        pe = val.get('PE_TTM', 0)
        pb = val.get('PB_MRQ', 0)
        mkt = val.get('TOTAL_MARKET_CAP', 0) / 1e8
        sector = val.get('BOARD_NAME', '')[:15]
        pe_str = f"{pe:.1f}" if pe and pe > 0 else "N/A"
        print(f"{r['name']:<10} {r['close']:<8.2f} {pe_str:<8} {pb:<6.2f} {mkt:<10.0f} {sector}")
    else:
        print(f"{r['name']:<10} {r['close']:<8.2f} N/A    N/A   N/A       N/A")

# 保存完整数据
import json
save_data = []
for r in stock_20:
    save_data.append({
        'code': r['code'],
        'name': r['name'],
        'close': r['close'],
        'turn': r['turn'],
    })
with open('/tmp/semi_stocks_20.json', 'w') as f:
    json.dump(save_data, f, ensure_ascii=False, indent=2)

print(f"\n\n共筛选出 {len(stock_20)} 只股价<=20元的半导体个股")