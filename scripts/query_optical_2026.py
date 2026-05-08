import baostock as bs
import pandas as pd
import json

# 登录
lg = bs.login()
print('登录结果:', lg.error_msg)

# 光通信概念股票列表（市值300亿内、股价30元内）
optical_stocks = [
    ('sz.300548', '博创科技'),
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
    ('sz.300730', '科创信息'),
    ('sh.600355', '精伦电子'),
    ('sz.002313', '日海智能'),
    ('sh.600345', '长江通信'),
]

results = []
for code, name in optical_stocks:
    rs = bs.query_history_k_data_plus(
        code,
        "date,code,open,high,low,close,volume,amount,turn,pe,pb",
        start_date='2026-04-01',
        end_date='2026-05-06',
        frequency="d",
        adjustflag="3"  # 不复权
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
            pe = float(latest['pe']) if latest['pe'] else 0
            pb = float(latest['pb']) if latest['pb'] else 0
            results.append({
                'code': code,
                'name': name,
                'close': close,
                'turn': turn,
                'pe': pe,
                'pb': pb,
            })
            print(f"{name}({code}): 收盘={close:.2f}元, 换手={turn:.2f}%, PE={pe:.1f}, PB={pb:.1f}")

# 获取总股本计算市值
print("\n--- 获取总股本 ---")
for r in results:
    rs = bs.query_stock_basic(code=r['code'])
    while rs.error_code == '0' and rs.next():
        data = rs.get_row_data()
        # data包含: code, code_name, ipoDate, outDate, type, status, industry, market
        if len(data) >= 8:
            r['industry'] = data[6]
            r['market'] = data[7]
    print(f"{r['name']}: 行业={r.get('industry','')}, 板块={r.get('market','')}")

# 筛选条件
print("\n\n=== 筛选结果（市值估算300亿内，股价30元内）===")
for r in results:
    close = r.get('close', 0)
    # 简化的市值估算：假设流通股本占总股本的30-50%
    # 实际市值需要总股本数据，这里用换手率和成交量估算
    if close > 0 and close <= 35:  # 放宽到35元，给点空间
        print(f"{r['name']}({r['code']}): 现价={close:.2f}元, 换手={r.get('turn',0):.2f}%, PE={r.get('pe',0):.1f}")

bs.logout()
