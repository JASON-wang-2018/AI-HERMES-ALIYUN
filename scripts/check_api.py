import subprocess
import json

def curl_json(url):
    r = subprocess.run(["curl","-s",url,"-H","User-Agent: Mozilla/5.0"],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {}

# 先测试原始数据
url = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f62&fs=m:90+t:2"
    "&fields=f12,f14,f2,f3,f62"
)
r = curl_json(url)

if r.get('data') and r.get('data').get('diff'):
    diff = r['data']['diff']
    print(f"总板块数: {len(diff)}")
    # 看前5条和后5条
    print("\n前5条:")
    for item in diff[:5]:
        print(f"  {item}")
    print("\n后5条:")
    for item in diff[-5:]:
        print(f"  {item}")
    
    # 统计f62的分布
    f62_vals = [item.get('f62', 0) for item in diff]
    print(f"\nf62统计: min={min(f62_vals):,}, max={max(f62_vals):,}, 负数数量={sum(1 for v in f62_vals if v < 0)}")