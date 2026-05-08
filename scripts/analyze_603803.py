import baostock as bs
import pandas as pd

lg = bs.login()

# 获取603803近一年日K数据
code = 'sh.603803'
rs = bs.query_history_k_data_plus(
    code,
    "date,code,open,high,low,close,volume,amount,turn,pe,pb",
    start_date='2025-05-01',
    end_date='2026-05-06',
    frequency="d",
    adjustflag="2"  # 前复权
)
print(f"错误码: {rs.error_code}, 错误信息: {rs.error_msg}")

data_list = []
while rs.error_code == '0' and rs.next():
    data_list.append(rs.get_row_data())
df = pd.DataFrame(data_list, columns=rs.fields)
print(f"获取到 {len(df)} 条数据")
print(df.tail(10).to_string())

# 保存数据
df.to_csv('/tmp/603803_kline.csv', index=False)
print("\n数据已保存到 /tmp/603803_kline.csv")

# 基本面信息
print("\n=== 基本信息 ===")
rs = bs.query_stock_basic(code=code)
while rs.error_code == '0' and rs.next():
    print(rs.get_row_data())

bs.logout()
