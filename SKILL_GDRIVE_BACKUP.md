# Google Drive 数据源备份（2026-05-12）
# 来源：~/.hermes/skills/a-stock-analysis/SKILL.md Step1数据采集部分
# Jason决定弃用，改为纯在线采集

## 来源A：Google Drive 通达信 .day 文件（离线数据）

Jason 的 Google Drive 里有一份通达信离线数据（文件夹 `vipdoc`），可作为数据源。

**目录结构（只读 sh/sz/bj）：**
```
vipdoc/
  sh/lday/   # 上海A股日线
  sz/lday/   # 深圳A股日线
  bj/lday/   # 北交所日线
```

**TDX .day 文件格式（32字节/条，小端序）：**
```python
import struct, datetime, google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# ── 1. 刷新 Google Drive token ──
with open('/home/admin/.hermes/google_token.json') as f:
    token_info = json.load(f)
creds = Credentials.from_authorized_user_info(info=token_info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
request = google.auth.transport.requests.Request()
creds.refresh(request)
service = build('drive', 'v3', credentials=creds)

# ── 2. 搜索文件ID ──
# 用 raw query 精确匹配文件名
results = service.files().list(
    q="name='sz000600.day'",
    fields="files(id,name,modifiedTime)",
    pageSize=5
).execute()
files = results.get('files', [])
# 取最新版本（modifiedTime 最晚）
latest = sorted(files, key=lambda x: x['modifiedTime'], reverse=True)[0]
file_id = latest['id']

# ── 3. 下载文件 ──
request = service.files().get_media(fileId=file_id)
fh = io.FileIO('/tmp/sz000600.day', 'wb')
downloader = MediaIoBaseDownload(fh, request)
done = False
while not done:
    _, done = downloader.next_chunk()

# ── 4. 解析 TDX .day（二进制，32字节/条）──
def parse_tdx_day(path):
    # ⚠️ 日期字段是 YYYYMMDD 整数，不是"天数偏移1990-01-01"
    records = []
    with open(path, 'rb') as f:
        while True:
            data = f.read(32)
            if len(data) < 32: break
            d0,d1,d2,d3,d4,d5,d6,d7 = struct.unpack('<IIIIIIII', data)
            ds = str(d0)  # 例: '20150902'
            records.append({
                'date': datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8])),
                'open': d1/100.0, 'high': d2/100.0, 'low': d3/100.0,
                'close': d4/100.0, 'amount': d5, 'vol': d6
            })
    return records

records = parse_tdx_day('/tmp/sz000600.day')
closes = [r['close'] for r in records]
volumes = [r['vol'] for r in records]
```

**⚠️ 关键陷阱：TDX .day 日期格式不是天数偏移！**
- 错误假设：`date = datetime.date(1990,1,1) + timedelta(days=d0)` → OverflowError
- 正确解析：`ds = str(d0)` → `datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))`
- 原因：通达信将日期直接存为 `YYYYMMDD` 整数值（如 20150902 = 2015年9月2日）
