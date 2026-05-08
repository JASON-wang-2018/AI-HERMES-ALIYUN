import baostock as bs
import pandas as pd

# 登录
lg = bs.login()
print('登录结果:', lg.error_msg)

# 获取所有股票列表
rs = bs.query_all_stock()
data_list = []
while (rs.error_code == '0') & rs.next():
    data_list.append(rs.get_row_data())
df = pd.DataFrame(data_list, columns=rs.fields)
print('股票总数:', len(df))
print(df.head(10))

# 筛选上海和深圳交易所的股票
df = df[df['code'].str.startswith(('sh.6', 'sz.0', 'sz.3'))]
print('A股数量:', len(df))

# 获取最新行情
rs = bs.query_realtime_quotes(df['code'].tolist())
print('实时行情查询:', rs.error_msg)

data_list = []
while (rs.error_code == '0') & rs.next():
    data_list.append(rs.get_row_data())
quotes = pd.DataFrame(data_list, columns=rs.fields)
print('行情数量:', len(quotes))
print(quotes[['code', 'name', 'price', 'market_capital', 'pe']].head(20))

bs.logout()