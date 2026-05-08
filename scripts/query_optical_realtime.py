import baostock as bs
import pandas as pd
import json

# 登录
lg = bs.login()
print('登录结果:', lg.error_msg)

# 获取日期
rs = bs.query_trade_dates(start_date='2026-05-05', end_date='2026-05-07')
cal_list = []
while rs.error_code == '0' and rs.next():
    cal_list.append(rs.get_row_data())
print('日历:', cal_list)

# 获取日K数据 - 测试几只光通信股票
codes = ['sz.300548', 'sh.600487', 'sz.002281', 'sh.600498', 'sz.000988', 'sh.603083']
results = []

for code in codes:
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
        latest = df.iloc[-1]
        results.append({
            'code': code,
            'name': latest['code'],
            'close': float(latest['close']) if latest['close'] else 0,
            'high': float(latest['high']) if latest['high'] else 0,
            'low': float(latest['low']) if latest['low'] else 0,
            'volume': int(latest['volume']) if latest['volume'] else 0,
            'turn': float(latest['turn']) if latest['turn'] else 0,
        })
        print(f"{code}: 收盘价={latest['close']}, 换手率={latest['turn']}%")

bs.logout()

# 获取总股本计算市值
print("\n--- 市值估算 ---")
for r in results:
    # 简化：取最新价估算
    print(f"{r['code']}: 收盘价={r['close']:.2f}元")
