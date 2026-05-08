import pandas as pd

# 通达信XLS文件，GBK编码，制表符分隔
file_path = '/home/admin/.hermes/cache/documents/doc_93d64a3a969a_260507-999999.xls'

# 读取文件
with open(file_path, 'r', encoding='gbk') as f:
    lines = f.readlines()

# 清理空白行
lines = [l for l in lines if l.strip() and not l.startswith('\r')]

print(f"总行数: {len(lines)}")

# 找表头行
header_line = None
data_start = 0
for i, line in enumerate(lines):
    if '时间' in line and '开盘' in line:
        header_line = line
        data_start = i + 1
        break

print(f"表头: {header_line.strip() if header_line else '未找到'}")
print(f"数据起始行: {data_start}")

# 解析表头
if header_line:
    headers = header_line.replace('\r', '').replace('\n', '').split('\t')
    headers = [h.strip() for h in headers if h.strip()]
    print(f"列名: {headers}")

# 解析数据
data_lines = lines[data_start:]
print(f"\n数据行数: {len(data_lines)}")

rows = []
for line in data_lines:
    line = line.replace('\r', '').replace('\n', '')
    cols = line.split('\t')
    if len(cols) >= 6 and cols[0].strip():
        try:
            rows.append([c.strip() for c in cols])
        except:
            pass

print(f"解析行数: {len(rows)}")

# 创建DataFrame
df = pd.DataFrame(rows)
if len(df) > 0:
    # 设置列名
    if header_line:
        col_names = header_line.replace('\r', '').replace('\n', '').split('\t')
        col_names = [c.strip() for c in col_names if c.strip()]
        if len(col_names) == len(df.columns):
            df.columns = col_names
    
    print("\n前10行:")
    print(df.head(10).to_string())
    
    print("\n后10行:")
    print(df.tail(10).to_string())
    
    print(f"\n日期范围: {df.iloc[0, 0]} ~ {df.iloc[-1, 0]}")
    
    # 保存为CSV
    csv_path = '/tmp/999999_kline.csv'
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\n已保存到: {csv_path}")