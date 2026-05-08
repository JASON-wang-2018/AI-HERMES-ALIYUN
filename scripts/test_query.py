import baostock as bs
import pandas as pd

lg = bs.login()

# 只测试几只重点股票
test_stocks = [
    ('sz.002491', '铭普光磁'),
    ('sh.600487', '亨通光电'),
    ('sz.300913', '兆龙互连'),
    ('sh.603083', '剑桥科技'),
    ('sh.600522', '中天科技'),
    ('sz.300548', '长芯博创'),
]

results = []
for code, name in test_stocks:
    print(f"\n查询 {name}({code})...")
    rs = bs.query_history_k_data_plus(
        code,
        "date,code,open,high,low,close,volume,amount,turn,pe,pb",
        start_date='2026-04-01',
        end_date='2026-05-06',
        frequency="d"
    )
    print(f"  错误码: {rs.error_code}, 错误信息: {rs.error_msg}")
    data_list = []
    while rs.error_code == '0' and rs.next():
        data_list.append(rs.get_row_data())
    print(f"  数据条数: {len(data_list)}")
    if data_list:
        df = pd.DataFrame(data_list, columns=rs.fields)
        print(df.tail(3).to_string())
        latest = df.iloc[-1]
        results.append({
            'code': code,
            'name': name,
            'close': float(latest['close']) if latest['close'] else 0,
        })

print(f"\n\n总共获取到 {len(results)} 只股票的数据")
for r in results:
    print(f"{r['name']}: {r['close']}")

bs.logout()
