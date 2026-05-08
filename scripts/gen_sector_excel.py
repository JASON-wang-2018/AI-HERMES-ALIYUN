import pandas as pd
import baostock as bs
import subprocess
import json
import urllib.parse
from datetime import datetime

def curl_json(url):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# 获取今天日期
today = datetime.now().strftime('%Y-%m-%d')

# 东财板块资金流API
# 按主力净流入排序，取前200条
url = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f62&fs=m:90+t:2"
    "&fields=f12,f14,f2,f3,f62,f184"
)
r = curl_json(url)

data_list = []
if r.get('data') and r.get('data').get('diff'):
    for item in r['data']['diff']:
        data_list.append({
            '板块代码': item.get('f12', ''),
            '板块名称': item.get('f14', ''),
            '最新价': item.get('f2', 0),
            '涨跌幅(%)': item.get('f3', 0),
            '主力净流入(万元)': item.get('f62', 0),
            '主力净流入(万元)_abs': abs(item.get('f62', 0)),
        })

df = pd.DataFrame(data_list)

# 按主力净流入排序
df_in = df[df['主力净流入(万元)'] > 0].sort_values('主力净流入(万元)', ascending=False).reset_index(drop=True)
df_out = df[df['主力净流入(万元)'] < 0].sort_values('主力净流入(万元)').reset_index(drop=True)

# 添加排名
df_in.insert(0, '排名', range(1, len(df_in)+1))
df_out.insert(0, '排名', range(1, len(df_out)+1))

# 格式化涨跌幅
df_in['涨跌幅(%)'] = df_in['涨跌幅(%)'] / 100
df_out['涨跌幅(%)'] = df_out['涨跌幅(%)'] / 100

print(f"主力净流入板块: {len(df_in)} 条")
print(f"主力净流出板块: {len(df_out)} 条")

# 输出Excel
output_path = f'/home/admin/stock_knowledge/reports/板块资金流_{today}.xlsx'

with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    # 概况
    summary = pd.DataFrame({
        '指标': ['报告日期', '统计时间', '净流入板块数', '净流出板块数', '主力净流入合计(万元)', '主力净流出合计(万元)'],
        '数值': [today, datetime.now().strftime('%H:%M:%S'), len(df_in), len(df_out), 
                 f"{df_in['主力净流入(万元)'].sum():,.0f}", 
                 f"{df_out['主力净流入(万元)'].sum():,.0f}"]
    })
    summary.to_excel(writer, sheet_name='概况', index=False)
    
    # 主力净流入TOP
    df_in.to_excel(writer, sheet_name='主力净流入', index=False)
    
    # 主力净流出
    df_out.to_excel(writer, sheet_name='主力净流出', index=False)
    
    # 完整数据
    df_full = df.sort_values('主力净流入(万元)', ascending=False).reset_index(drop=True)
    df_full.insert(0, '排名', range(1, len(df_full)+1))
    df_full.to_excel(writer, sheet_name='完整数据', index=False)

print(f"\n✅ Excel已生成: {output_path}")

# 打印TOP10
print(f"\n=== 主力净流入 TOP10 ===")
print(df_in[['排名', '板块名称', '主力净流入(万元)', '涨跌幅(%)']].head(10).to_string(index=False))

print(f"\n=== 主力净流出 TOP10 ===")
print(df_out[['排名', '板块名称', '主力净流入(万元)', '涨跌幅(%)']].head(10).to_string(index=False))
