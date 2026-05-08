import subprocess
import json
import urllib.parse
import pandas as pd
from datetime import datetime

def curl_json(url):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# 测试几个字段
url = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=5&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f3&fs=m:0+t:6+f:!50"
    "&fields=f12,f14,f2,f3,f62,f170,f23,f168,f9,f10"
)
r = curl_json(url)

if r.get('data') and r.get('data').get('diff'):
    print("原始字段测试:")
    for item in r['data']['diff'][:10]:
        print(f"  {item['f14']}: f2={item['f2']}, f170={item['f170']}, f23={item['f23']}, f9={item.get('f9')}, f10={item.get('f10')}")