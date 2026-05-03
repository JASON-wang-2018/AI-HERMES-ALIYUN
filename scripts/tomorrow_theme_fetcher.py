#!/usr/bin/env python3
"""
明日主题前瞻采集脚本
采集 CLS.cn 明日主题前瞻 页面文章，提取关键主题信息
"""
import requests
import re
import sys
import json
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.cls.cn/",
}

def fetch_list_page():
    """获取明日主题前瞻最新一期文章ID"""
    url = "https://www.cls.cn/subject/1160"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = 'utf-8'
    # 提取所有文章ID
    article_ids = re.findall(r'/article/(\d+)', resp.text)
    # 去重
    article_ids = list(dict.fromkeys(article_ids))
    print(f"Found {len(article_ids)} articles, latest: {article_ids[:3]}")
    return article_ids

def fetch_article_detail(article_id):
    """获取单篇文章详情"""
    url = f"https://api3.cls.cn/share/article/{article_id}?sv=8.7.7&app=cailianpress&os=android"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    data = resp.json()
    
    if data.get('code') != 0:
        print(f"API error: {data}")
        return None
    
    content = data['data']['content']
    # 清理HTML实体
    content = content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    content = re.sub(r'<[^>]+>', '', content)  # 移除HTML标签
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()

def extract_themes(content):
    """从文章内容提取主题信息"""
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    
    themes = []  # 主题列表
    current_theme = None
    current_body = []
    
    for line in lines:
        # 标题行：序号 + 主题名 或 【行业/主题】
        title_match = re.match(r'^(【[^】]+】|[\d①②③④⑤⑥⑦⑧⑨⑩]+[.、:]?\s*)(.+)', line)
        if title_match and len(line) < 80:
            # 保存上一个主题
            if current_theme:
                themes.append({
                    'title': current_theme,
                    'body': '\n'.join(current_body[:6])  # 最多6行
                })
            current_theme = line
            current_body = []
        elif current_theme:
            current_body.append(line)
        else:
            # 没有主题时跳过元信息行
            if any(kw in line for kw in ['作者', '来源', '时间', '责任编辑', '免责声明']):
                continue
            current_body.append(line)
    
    # 最后一个主题
    if current_theme:
        themes.append({
            'title': current_theme,
            'body': '\n'.join(current_body[:6])
        })
    
    return themes

def parse_article(content):
    """解析整篇文章，返回结构化数据"""
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    
    # 取前100字判断日期
    preview = content[:200]
    date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', preview)
    article_date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}" if date_match else ""
    
    # 提取主题
    themes = extract_themes(content)
    
    # 提取关键词（出现频率高的词）
    words = re.findall(r'[\u4e00-\u9fa5]{2,6}(?:概念|行业|板块|产业链|龙头|涨价|政策|布局|机会)', content)
    word_freq = {}
    for w in words:
        word_freq[w] = word_freq.get(w, 0) + 1
    top_keywords = sorted(word_freq.items(), key=lambda x: -x[1])[:15]
    
    return {
        'article_date': article_date,
        'themes': themes,
        'keywords': top_keywords,
        'raw_preview': content[:500],
    }

def main():
    print(f"=== 明日主题前瞻采集 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    
    # 1. 获取文章列表
    article_ids = fetch_list_page()
    if not article_ids:
        print("无法获取文章列表")
        sys.exit(1)
    
    latest_id = article_ids[0]
    print(f"\n>>> 采集最新一期: {latest_id}")
    
    # 2. 获取详情
    content = fetch_article_detail(latest_id)
    if not content:
        sys.exit(1)
    
    print(f"\n--- 文章前800字预览 ---")
    print(content[:800])
    print("...\n")
    
    # 3. 解析结构
    parsed = parse_article(content)
    print(f"文章日期: {parsed['article_date']}")
    print(f"提取到 {len(parsed['themes'])} 个主题")
    for i, t in enumerate(parsed['themes'][:5], 1):
        print(f"\n  主题{i}: {t['title']}")
        print(f"  要点: {t['body'][:150]}")
    
    print(f"\n高频关键词: {[w for w,_ in parsed['keywords'][:10]]}")

if __name__ == '__main__':
    main()
