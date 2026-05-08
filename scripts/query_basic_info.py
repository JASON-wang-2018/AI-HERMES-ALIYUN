import baostock as bs
import pandas as pd

lg = bs.login()

# 重点关注的<=30元股票
key_stocks = [
    ('sz.002638', '勤上股份'),
    ('sz.300366', '东方国信'),
    ('sz.300310', '宜通世纪'),
    ('sz.300025', '华星创业'),
    ('sz.000936', '华西股份'),
    ('sz.002313', '日海智能'),
    ('sz.300565', '科信技术'),
    ('sh.600775', '南京熊猫'),
    ('sh.603803', '瑞斯康达'),
    ('sz.003015', '日久光电'),
    ('sh.605189', '富春染织'),
    ('sz.002491', '铭普光磁'),
    ('sh.600353', '旭光电子'),
    ('sz.002436', '兴森科技'),
    ('sh.600522', '中天科技'),
    ('sz.002922', '伊戈尔'),
]

# 获取基本面数据（总股本）
print("=== 基本信息与市值估算 ===")
for code, name in key_stocks:
    rs = bs.query_stock_basic(code=code)
    basic_info = []
    while rs.error_code == '0' and rs.next():
        basic_info = rs.get_row_data()
    
    # 获取最新日K（计算市值用）
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
    
    if data_list and basic_info:
        df = pd.DataFrame(data_list, columns=rs.fields)
        latest = df.iloc[-1]
        close = float(latest['close']) if latest['close'] else 0
        
        # basic_info: [code, code_name, ipoDate, outDate, type, status, industry, market]
        industry = basic_info[6] if len(basic_info) > 6 else ''
        print(f"{name}({code}): 收盘={close:.2f}元, 行业={industry}")

bs.logout()
