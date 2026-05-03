import sqlite3, json
conn = sqlite3.connect('database/daily_market.db')
c = conn.cursor()
c.execute('SELECT review_type, title, key_points FROM daily_review WHERE review_type="焦点复盘" ORDER BY trade_date DESC LIMIT 1')
row = c.fetchone()
if row:
    print(f'类型: {row[0]}')
    print(f'标题: {row[1]}')
    kp = json.loads(row[2]) if row[2] else {}
    if kp:
        for k, v in kp.items():
            if v: print(f'{k}: {v[:100]}...' if len(v) > 100 else f'{k}: {v}')
    else:
        print('⚠️ 焦点复盘提取失败，仅采集到标题')
else:
    print('无数据')
conn.close()