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

DATE = '2026-05-06'

# 获取半导体概念板块成分股
# 先找半导体概念板块
url_concept = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f3&fs=m:90+t:3"
    "&fields=f12,f14,f2,f3"
)
r_con = curl_json(url_concept)

# 找半导体相关的概念板块代码
semi_board_codes = []
if r_con.get('data') and r_con['data'].get('diff'):
    for item in r_con['data']['diff']:
        name = item.get('f14', '')
        code = item.get('f12', '')
        if any(kw in name for kw in ['半导体', '芯片', '集成电路', '光刻', '硅片', '封装']):
            print(f"找到: {name} ({code})")
            semi_board_codes.append((code, name))

# 获取各概念板块的成分股
all_semi_stocks = {}
for board_code, board_name in semi_board_codes[:5]:  # 取前5个板块
    url_board = (
        f"https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
        f"&fltt=2&invt=2&fid=f3&fs=m:90+t:3+f:{board_code}"
        f"&fields=f12,f14,f2,f3,f170,f9,f10"
    )
    r = curl_json(url_board)
    if r.get('data') and r['data'].get('diff'):
        for item in r['data']['diff']:
            code = item.get('f12', '')
            if code not in all_semi_stocks:
                all_semi_stocks[code] = {
                    'code': code,
                    'name': item.get('f14', ''),
                    'close': item.get('f2', 0),
                    'pct_chg': item.get('f3', 0),
                    'mkt_cap': item.get('f170', 0),
                    'pe': item.get('f9', 0),
                    'pb': item.get('f10', 0),
                    'boards': [board_name]
                }
            else:
                all_semi_stocks[code]['boards'].append(board_name)

print(f"\n半导体相关股票总数: {len(all_semi_stocks)}")

# 转换市值为亿元
# f170字段测试：如果f2=14.58是元，那f170如果也是元，需要/1e8
# 测试：宏川智慧 f170=4731935，按元算=473万，按万算=47.3亿（接近实际60亿）
# 所以f170单位应该是"万元"

filtered = []
for code, s in all_semi_stocks.items():
    close_yuan = s['close']  # f2直接是元
    mkt_wan = s['mkt_cap']  # f170是万元
    if mkt_wan <= 0:
        mkt_yi = 0
    elif mkt_wan > 10000000:  # >100亿的可能单位已经是元
        mkt_yi = mkt_wan / 1e8
    else:
        mkt_yi = mkt_wan / 10000  # 万元转亿
    
    if 0 < close_yuan <= 20 and mkt_yi <= 200:
        s['mkt_yi'] = mkt_yi
        pe = s['pe']
        filtered.append({
            'code': code,
            'name': s['name'],
            'close': close_yuan,
            'mkt_yi': mkt_yi,
            'pe': pe if pe and pe > 0 else None,
            'pb': s['pb'] if s['pb'] and s['pb'] > 0 else None,
            'boards': ','.join(s['boards'][:3])
        })

filtered.sort(key=lambda x: x['mkt_yi'], reverse=True)

print(f"\n筛选后（股价<=20元 & 市值<=200亿）: {len(filtered)} 只")
print(f"\n{'名称':<10} {'代码':<10} {'最新价':<8} {'PE':<8} {'PB':<6} {'市值(亿)':<10} {'概念板块'}")
print("-" * 90)
for s in filtered[:40]:
    pe_str = f"{s['pe']:.1f}" if s['pe'] else "N/A"
    pb_str = f"{s['pb']:.2f}" if s['pb'] else "N/A"
    print(f"{s['name']:<10} {s['code']:<10} {s['close']:<8.2f} {pe_str:<8} {pb_str:<6} {s['mkt_yi']:<10.0f} {s['boards'][:30]}")

# 生成Excel
df = pd.DataFrame(filtered)
output_path = f'/home/admin/stock_knowledge/reports/半导体个股筛选_{DATE}.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='半导体个股', index=False)
print(f"\n✅ Excel已生成: {output_path}")