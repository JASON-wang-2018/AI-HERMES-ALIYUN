import baostock as bs
import pandas as pd

lg = bs.login()

# 光通信概念股票列表
optical_stocks = [
    ('sz.300548', '长芯博创'),
    ('sz.002491', '铭普光磁'),
    ('sz.300913', '兆龙互连'),
    ('sz.000988', '华工科技'),
    ('sz.002281', '光迅科技'),
    ('sh.603083', '剑桥科技'),
    ('sh.600487', '亨通光电'),
    ('sh.600522', '中天科技'),
    ('sh.600498', '烽火通信'),
    ('sh.601869', '长飞光纤'),
    ('sh.605189', '富春染织'),
    ('sz.000936', '华西股份'),
    ('sz.002922', '伊戈尔'),
    ('sz.003015', '日久光电'),
    ('sz.002638', '勤上股份'),
    ('sh.603803', '瑞斯康达'),
    ('sh.600345', '长江通信'),
    ('sh.600775', '南京熊猫'),
    ('sz.002313', '日海智能'),
    ('sz.300366', '东方国信'),
    ('sz.002436', '兴森科技'),
    ('sz.300310', '宜通世纪'),
    ('sz.300025', '华星创业'),
    ('sh.600353', '旭光电子'),
    ('sz.300565', '科信技术'),
]

results = []
for code, name in optical_stocks:
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
                'df': df,  # 保留完整数据
            })

# 筛选股价<=30元的
print("=== 光通信概念个股（股价<=30元）===")
print(f"{'名称':<12} {'代码':<12} {'最新价':<10} {'换手%':<8}")
print("-" * 45)
for r in sorted(results, key=lambda x: x['close']):
    if r['close'] > 0 and r['close'] <= 30:
        print(f"{r['name']:<12} {r['code']:<12} {r['close']:<10.2f} {r['turn']:<8.2f}")

print("\n=== 股价30-50元区间 ===")
print(f"{'名称':<12} {'代码':<12} {'最新价':<10} {'换手%':<8}")
print("-" * 45)
for r in sorted(results, key=lambda x: x['close']):
    if r['close'] > 30 and r['close'] <= 50:
        print(f"{r['name']:<12} {r['code']:<12} {r['close']:<10.2f} {r['turn']:<8.2f}")

print("\n=== 股价>50元（高位风险） ===")
print(f"{'名称':<12} {'代码':<12} {'最新价':<10}")
print("-" * 35)
for r in sorted(results, key=lambda x: x['close']):
    if r['close'] > 50:
        print(f"{r['name']:<12} {r['code']:<12} {r['close']:<10.2f}")

# 保存结果供后续使用
import json
with open('/tmp/optical_stocks_2026.json', 'w') as f:
    json.dump([{k: v for k, v in r.items() if k != 'df'} for r in results], f, ensure_ascii=False, indent=2)

bs.logout()
