import baostock as bs
import pandas as pd

# 登录
lg = bs.login()
print('登录结果:', lg.error_msg)

# 获取行业分类
rs = bs.query_stock_industry()
print('行业数据:', rs.error_msg)

data_list = []
while (rs.error_code == '0') & rs.next():
    data_list.append(rs.get_row_data())
df = pd.DataFrame(data_list, columns=rs.fields)
print('行业数量:', len(df))
print(df.head(10))

# 筛选光通信相关行业
optical = df[df['industry'].str.contains('光通信|光模块|光器件|光纤', na=False)]
print('\n光通信相关行业:')
print(optical)

bs.logout()