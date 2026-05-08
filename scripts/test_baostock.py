import baostock as bs
import pandas as pd

# 登录
lg = bs.login()
print('登录结果:', lg.error_msg)

# 测试获取数据
print("\n--- 测试K线获取 ---")

# 先查交易日历
rs = bs.query_trade_dates(start_date='2026-01-01', end_date='2026-05-07')
dates = []
while rs.error_code == '0' and rs.next():
    dates.append(rs.get_row_data())
print(f"2026年交易日数量: {len(dates)}")

# 测试单只股票
print("\n--- 测试博创科技(300548) ---")
rs = bs.query_history_k_data_plus(
    "sz.300548",
    "date,code,open,high,low,close,volume,amount,turn",
    start_date='2026-03-01',
    end_date='2026-05-06',
    frequency="d"
)
print('错误码:', rs.error_code)
print('错误信息:', rs.error_msg)
data_list = []
while rs.error_code == '0' and rs.next():
    data_list.append(rs.get_row_data())
print(f"获取到{len(data_list)}条数据")
if data_list:
    df = pd.DataFrame(data_list, columns=rs.fields)
    print(df.tail(5))

# 获取stock_basic信息
print("\n--- 股票基本信息 ---")
rs = bs.query_stock_basic(code="sz.300548")
while rs.error_code == '0' and rs.next():
    print(rs.get_row_data())

# 列出所有股票
print("\n--- 获取所有股票列表 ---")
rs = bs.query_all_stock()
all_stocks = []
while rs.error_code == '0' and rs.next():
    all_stocks.append(rs.get_row_data())
print(f"总股票数: {len(all_stocks)}")
# 筛选sz开头的
sz_stocks = [s for s in all_stocks if s[0].startswith('sz.')]
sh_stocks = [s for s in all_stocks if s[0].startswith('sh.')]
print(f"深圳: {len(sz_stocks)}, 上海: {len(sh_stocks)}")
print("示例:", sz_stocks[:3])

bs.logout()
