import subprocess
import json
import re
import pandas as pd
from datetime import datetime, timedelta

def curl_text(url, timeout=20):
    r = subprocess.run(["curl","-s","--connect-timeout", str(timeout), "-L",
                        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        url], capture_output=True, text=True, timeout=timeout+5)
    return r.stdout

def extract_content(html):
    """提取正文内容"""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    html = re.sub(r'\s+', ' ', html).strip()
    return html

def get_list():
    """获取财经早餐列表"""
    list_url = "https://stock.eastmoney.com/a/czpnc.html"
    html = curl_text(list_url)
    
    # 提取topic.eastmoney.com链接
    pattern = r'<span>(\d{2}月\d{2}日)</span>&nbsp;<a href="(https://topic\.eastmoney\.com/detail/[^"]+)"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html)
    
    articles = []
    for date_label, href, title in matches:
        title = title.replace('&#183;', '·').replace('&amp;', '&').strip()
        # 提取日期: 盘前必读5月7日 -> 2026-05-07
        date_match = re.search(r'(\d+)月(\d+)日', title)
        if date_match:
            month, day = date_match.groups()
            year = '2026'
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            date_str = ''
        
        articles.append({
            'title': title,
            'url': href,
            'date': date_str,
            'date_label': date_label
        })
    
    return articles

def find_finance_url(list_html, date_str, title):
    """从列表页HTML中查找对应的finance.eastmoney.com URL"""
    # 列表页中的文章URL格式: https://finance.eastmoney.com/a/YYYYMMDDXXXXXXXX.html
    # 日期是文章的实际发布日期
    # 构建搜索模式
    date_for_url = date_str.replace('-', '')  # 2026-05-07 -> 20260507
    
    # 在HTML中搜索包含此日期的finance链接
    pattern = f'href="(https://finance\\.eastmoney\\.com/a/{date_for_url}\\d+\\.html)"'
    match = re.search(pattern, list_html)
    if match:
        return match.group(1)
    return None

def fetch_article_content(url):
    """抓取文章完整内容"""
    html = curl_text(url)
    if not html:
        return None
    content = extract_content(html)
    
    # 找正文开始位置
    keywords = ['东方财富财经早餐', '财经早餐', '盘前必读']
    for kw in keywords:
        idx = content.find(kw)
        if idx >= 0:
            return content[idx:idx+10000]
    return content[:10000]

# 主流程
print("=" * 60)
print("东方财富财经早餐 采集器")
print("=" * 60)

# 1. 获取列表
list_html = curl_text("https://stock.eastmoney.com/a/czpnc.html")
print(f"\n[1] 获取列表页...")
articles = get_list()
print(f"    ✅ 找到 {len(articles)} 篇早餐")

for art in articles:
    print(f"    {art['date']} | {art['title']}")

# 2. 为每篇文章查找完整的finance.eastmoney.com链接
print(f"\n[2] 查找完整文章链接...")
for art in articles:
    finance_url = find_finance_url(list_html, art['date'], art['title'])
    art['finance_url'] = finance_url
    if finance_url:
        print(f"    ✅ {art['date_label']}: {finance_url}")
    else:
        print(f"    ⚠️ {art['date_label']}: 未找到finance链接")

# 3. 抓取最新几篇文章
print(f"\n[3] 抓取最新文章内容...")
for art in articles[:3]:  # 只抓前3篇
    if art.get('finance_url'):
        print(f"\n    抓取: {art['title']}")
        body = fetch_article_content(art['finance_url'])
        if body:
            print(f"    ✅ 内容长度: {len(body)} 字符")
            # 保存
            safe_title = re.sub(r'[^\w\u4e00-\u9fff]', '_', art['title'])[:30]
            save_path = f'/home/admin/stock_knowledge/reports/财经早餐_{art["date"]}_{safe_title}.txt'
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(f"标题: {art['title']}\n")
                f.write(f"日期: {art['date']}\n")
                f.write(f"列表链接: {art['url']}\n")
                f.write(f"文章链接: {art['finance_url']}\n")
                f.write("=" * 60 + "\n")
                f.write(body)
            print(f"    ✅ 已保存: {save_path}")

# 4. 保存完整列表
df = pd.DataFrame(articles)
list_path = '/home/admin/stock_knowledge/reports/财经早餐列表.csv'
df.to_csv(list_path, index=False, encoding='utf-8-sig')
print(f"\n✅ 链接列表已保存: {list_path}")

print("\n" + "=" * 60)
print("采集完成！")
print("=" * 60)