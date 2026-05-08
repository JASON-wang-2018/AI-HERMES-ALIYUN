import subprocess
import json
import urllib.parse
import pandas as pd
from datetime import datetime

def curl_json(url):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# 用东财股票列表API筛选：半导体相关 + 市值200亿内 + 股价20元内
# fs参数：m:0+t:6+ff_industry_code 半导体行业
# 或者直接用概念板块筛选

# 先获取半导体概念板块的个股
# f12=代码 f14=名称 f2=最新价 f3=涨跌幅 f62=主力净流入 f170=总市值 f23=流通市值

DATE = '2026-05-06'

# 方法1：用东财选股器API - 半导体行业筛选
url_stocklist = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=500&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f3&fs=m:0+t:6+f:!50"  # t:6=半导体
    "&fields=f12,f14,f2,f3,f62,f170,f23,f168,f10,f9"
)
r = curl_json(url_stocklist)

all_stocks = []
if r.get('data') and r.get('data').get('diff'):
    for item in r['data']['diff']:
        close = item.get('f2', 0) / 100 if item.get('f2') else 0  # 分->元
        mkt_cap = item.get('f170', 0) / 100000000 if item.get('f170') else 0  # 分->亿
        circ_mkt = item.get('f23', 0) / 100000000 if item.get('f23') else 0
        pe = item.get('f9', 0)
        pb = item.get('f10', 0)
        
        all_stocks.append({
            'code': item.get('f12', ''),
            'name': item.get('f14', ''),
            'close': close,
            'pct_chg': item.get('f3', 0),
            'main_force': item.get('f62', 0) / 10000 if item.get('f62') else 0,  # 万元
            'mkt_cap': mkt_cap,
            'circ_mkt': circ_mkt,
            'pe': pe,
            'pb': pb,
            'main_force_yi': (item.get('f62', 0) / 100000000) if item.get('f62') else 0
        })

print(f"获取到 {len(all_stocks)} 只股票")

# 筛选：股价<=20元 且 市值<=200亿
filtered = [s for s in all_stocks if 0 < s['close'] <= 20 and s['mkt_cap'] <= 200 and s['mkt_cap'] > 0]

print(f"\n筛选后（股价<=20元 & 市值<=200亿）: {len(filtered)} 只")

# 按市值排序
filtered.sort(key=lambda x: x['mkt_cap'], reverse=True)

print(f"\n{'名称':<10} {'代码':<10} {'最新价':<8} {'PE':<8} {'PB':<6} {'市值(亿)':<10} {'流通(亿)':<10} {'换手率':<8}")
print("-" * 80)
for s in filtered[:40]:
    pe_str = f"{s['pe']:.1f}" if s['pe'] and s['pe'] > 0 else "N/A"
    main_yi = s.get('main_force_yi', 0)
    main_str = f"{main_yi:+.2f}亿" if main_yi else "N/A"
    print(f"{s['name']:<10} {s['code']:<10} {s['close']:<8.2f} {pe_str:<8} {s['pb']:<6.2f} {s['mkt_cap']:<10.0f} {s['circ_mkt']:<10.0f} {main_str}")

# 保存数据
df = pd.DataFrame(filtered)
output_path = f'/home/admin/stock_knowledge/reports/半导体个股筛选_{DATE}.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='半导体个股', index=False)
print(f"\n✅ Excel已生成: {output_path}")