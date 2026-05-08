#!/usr/bin/env python3
"""
涨停复盘完整数据采集脚本
数据来源：东方财富搜索API + finance.eastmoney.com文章正文（Playwright渲染）
采集内容：
  - 午间涨停复盘（每日12:00左右，含涨停数量/封板率/连板龙头）
  - 收盘涨停复盘（每日16:00左右，含涨停数量/封板率/连板龙头）
  - 涨停股详细列表（数据宝/证券时报，含每只股的代码/收盘价/换手率/封单量/封单资金/行业）
输出：JSON（含全文+表格）+ Excel（含结构化数据）
"""

import urllib.request
import urllib.parse
import json
import re
import time
import sys
import os
import random
from datetime import datetime
from io import StringIO

VENV_PYTHON = '/home/admin/stock_knowledge/.venv/bin/python3'

def _safe_delay(seconds=3):
    time.sleep(random.uniform(seconds * 0.8, seconds * 1.5))


def _format_search_date(dt):
    """格式化日期为搜索用字符串，去掉前导0（东方财富搜索不用前导0）"""
    month = dt.month
    day = dt.day
    return f"{month}月{day}日"


def search_articles(keyword, max_pages=2, page_size=10):
    """通过东方财富搜索API查询涨停复盘相关文章（使用subprocess+curl保证URL编码正确）"""
    import subprocess
    results = []
    for page in range(1, max_pages + 1):
        param = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticle"],
            "client": "web",
            "clientVersion": "curr",
            "clientType": "web",
            "param": {
                "cmsArticle": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": page,
                    "pageSize": page_size,
                    "preTag": "<em>",
                    "postTag": "</em>"
                }
            }
        }
        # 使用subprocess+curl保证中文URL编码正确
        encoded = urllib.parse.quote(json.dumps(param, ensure_ascii=False), safe='')
        url = f"https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={encoded}"

        try:
            proc = subprocess.run(
                ['curl', '-s', '-A', 'Mozilla/5.0', url],
                capture_output=True, text=True, timeout=15
            )
            data = proc.stdout

            json_str = re.sub(r'^jQuery\(|\)$', '', data)
            parsed = json.loads(json_str)

            articles = parsed.get('result', {}).get('cmsArticle', [])
            for art in articles:
                results.append({
                    'title': re.sub(r'<[^>]+>', '', art.get('title', '')),
                    'date': art.get('date', ''),
                    'code': art.get('code', ''),
                    'url': f"https://finance.eastmoney.com/a/{art.get('code', '')}.html",
                    'content': re.sub(r'<[^>]+>', '', art.get('content', '')),
                    'media': art.get('mediaName', ''),
                })
            time.sleep(0.3)
        except Exception as e:
            print(f"  Search error: {e}")
    return results


def fetch_article_with_playwright(url):
    """使用Playwright抓取文章完整正文（支持JS动态渲染）"""
    import subprocess

    script = f'''
from playwright.sync_api import sync_playwright
import re

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-images"]
    )
    page = browser.new_page(viewport={{"width": 1280, "height": 3000}})
    try:
        page.goto("{url}", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(5000)
        text = page.inner_text("body")
        
        # Try to find the article table
        tables = page.query_selector_all("table")
        table_data = []
        for tbl in tables:
            headers = []
            rows_data = []
            # Get headers
            ths = tbl.query_selector_all("thead th")
            if ths:
                headers = [th.inner_text().strip() for th in ths]
            # Get rows
            trs = tbl.query_selector_all("tbody tr")
            if not trs:
                trs = tbl.query_selector_all("tr")
            for row in trs:
                cells = row.query_selector_all("td")
                if cells:
                    row_text = [c.inner_text().strip() for c in cells]
                    if any(c for c in row_text):
                        rows_data.append(row_text)
            if headers or rows_data:
                table_data.append({{"headers": headers, "rows": rows_data}})
        
        result = {{
            "text": text,
            "tables": table_data
        }}
        import json
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        import json
        print(json.dumps({{"error": str(e)}}, ensure_ascii=False))
    browser.close()
'''
    result = subprocess.run(
        [VENV_PYTHON, '-c', script],
        capture_output=True, text=True, timeout=45
    )
    if result.returncode != 0:
        return {"text": "", "tables": [], "error": result.stderr}

    try:
        return json.loads(result.stdout)
    except:
        return {"text": "", "tables": [], "error": result.stdout[:200]}


def parse_ztfp_summary(text):
    """解析涨停复盘摘要（午间/收盘通用）"""
    data = {}
    # 涨停数量
    m = re.search(r'共计?(\d+)股?涨停', text)
    if m:
        data['涨停总数'] = int(m.group(1))

    # 封板率
    m = re.search(r'封板率([\d.]+)%?', text)
    if m:
        data['封板率'] = float(m.group(1))

    # 触及涨停
    m = re.search(r'(\d+)只个股?盘中一度?触及?涨停', text)
    if m:
        data['触及涨停'] = int(m.group(1))

    # 龙头股
    m = re.search(r'[\u4e00-\u9fa5]{2,10}(\d+天?\d*板)', text)
    if m:
        data['连板龙头'] = m.group(0)

    # 提取连板信息
    m = re.findall(r'([\u4e00-\u9fa5]{2,8}\d+天\d+板)', text)
    if m:
        data['连板个股'] = m[:5]

    # 成交额
    m = re.search(r'成交[额量]([\d.]+[万亿]?)', text)
    if m:
        data['成交'] = m.group(0)

    # 指数涨跌
    m = re.findall(r'([\u4e00-\u9fa5]+指?)[涨跌]\s*([\d.]+)%?', text)
    if m:
        data['指数涨跌'] = [(idx[0], idx[1]) for idx in m[:3]]

    return data


def parse_zt_stock_table(text):
    """解析涨停股详细表格"""
    lines = text.split('\n')
    stocks = []
    current = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 匹配表格行：6位代码 + 名称 + 数字...
        m = re.match(r'^(\d{6})\s+([^\d]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.-]+)\s+([\d.-]+|[-])\s+([\u4e00-\u9fa5]+)', line)
        if m:
            code, name, close, turnover, seal_amount, seal_fund, industry = m.groups()
            if name and close and seal_amount != '-':
                stocks.append({
                    'code': code,
                    'name': name.strip(),
                    'close': float(close) if close != '-' else 0,
                    'turnover': float(turnover) if turnover != '-' else 0,
                    'seal_amount': float(seal_amount.replace(',', '')) if seal_amount not in ['-', ''] else 0,
                    'seal_fund': float(seal_fund.replace(',', '')) if seal_fund not in ['-', ''] else 0,
                    'industry': industry
                })
    return stocks


def collect_ztfp_full(date_str=None):
    """
    采集指定日期的完整涨停复盘数据
    date_str: 格式 '2026-05-07' 或 None（今天）
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    results = {
        'date': date_str,
        'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '午间涨停复盘': None,
        '收盘涨停复盘': None,
        '涨停股详细列表': []
    }

    # 日期格式：YYYY-MM-DD (e.g. '2026-05-07')
    out_dir = '/home/admin/stock_knowledge/reports'

    # === 1. 搜索午间涨停复盘 ===
    # 策略：不带日期搜"午间涨停复盘"（更稳定），然后按发布日期过滤
    print(f"\n[1] 搜索午间涨停复盘...")
    wj_results = search_articles("午间涨停复盘", max_pages=1, page_size=10)
    # 取发布日期 >= 查询日期 最早的一篇（最近当天）
    best_wj = None
    for r in wj_results:
        if r['date'][:10] >= date_str:
            best_wj = r
            break
    if not best_wj and wj_results:
        best_wj = wj_results[0]  # 备用：最新的

    print(f"    搜索返回: {len(wj_results)} 条，找到: {best_wj['title'] if best_wj else '无'}")

    if best_wj:
        print(f"  → 找到: [{best_wj['date']}] {best_wj['title']}")
        print(f"    摘要: {best_wj['content'][:120]}")
        results['午间涨停复盘'] = {
            'title': best_wj['title'],
            'date': best_wj['date'],
            'url': best_wj['url'],
            'summary': {},
            'full_text': best_wj['content']
        }
        # 抓全文（备用）
        _safe_delay(2)

    # === 2. 搜索收盘涨停复盘 ===
    # 策略：搜"涨停复盘"（含午间+收盘），排除午间，选发布日期最接近的一篇
    print(f"\n[2] 搜索收盘涨停复盘...")
    sb_results = search_articles("涨停复盘", max_pages=1, page_size=10)
    best_sb = None
    for r in sb_results:
        if '涨停复盘' in r['title'] and '午间' not in r['title']:
            if r['date'][:10] >= date_str:
                best_sb = r
                break
    if not best_sb and sb_results:
        for r in sb_results:
            if '涨停复盘' in r['title'] and '午间' not in r['title']:
                best_sb = r
                break
    if best_sb:
        print(f"    搜索返回: {len(sb_results)} 条，找到: {best_sb['title']}")

    if best_sb:
        print(f"  → 找到: [{best_sb['date']}] {best_sb['title']}")
        print(f"    来源: {best_sb['media']}")
        print(f"    摘要: {best_sb['content'][:120]}")
        results['收盘涨停复盘'] = {
            'title': best_sb['title'],
            'date': best_sb['date'],
            'url': best_sb['url'],
            'media': best_sb['media'],
            'summary': {},
            'full_text': best_sb['content']
        }
        _safe_delay(2)

    # === 3. 搜索涨停股详细列表 ===
    # 搜索涨停股详细列表（数据宝表格，发布时间晚于收盘复盘）
    # 策略：搜索"涨停股复盘"找最新N篇，然后过滤出含封单/封亿/一览等关键词
    print(f"\n[3] 搜索涨停股详细列表...")
    xq_results = search_articles("涨停股复盘", max_pages=2, page_size=15)

    detail_articles = []
    for r in xq_results:
        if '涨停' in r['title'] and ('封单' in r['title'] or '涨停股' in r['title'] or '一览' in r['title']):
            # 优先选发布日=查询日的，其次选最接近的
            art_date = r['date'][:10]
            detail_articles.append((art_date, r))

    # 按日期降序排列
    detail_articles.sort(key=lambda x: x[0], reverse=True)

    # 过滤：取发布日期>=查询日的前几条，或取最接近的一天
    today_arts = [(d, r) for d, r in detail_articles if d >= date_str]
    if today_arts:
        detail_articles = today_arts
    else:
        # 取最新的一篇（可能是前一个交易日的）
        if detail_articles:
            latest_date = detail_articles[0][0]
            detail_articles = [(d, r) for d, r in detail_articles if d == latest_date]

    print(f"  找到 {len(detail_articles)} 篇详细列表文章（最近: {detail_articles[0][0] if detail_articles else '无'}）")

    all_stocks = []
    for i, (art_date, art) in enumerate(detail_articles[:3]):  # 最多处理3篇
        print(f"\n  [{i+1}] 抓取详细数据: [{art['date']}] {art['title']}")
        print(f"      来源: {art['media']} | URL: {art['url']}")

        pw_result = fetch_article_with_playwright(art['url'])

        if pw_result.get('tables'):
            for tbl in pw_result['tables']:
                headers = tbl.get('headers', [])
                rows = tbl.get('rows', [])
                print(f"      → 表格: {len(rows)} 行数据")

                for row in rows:
                    if len(row) >= 6:
                        try:
                            stock = {
                                'code': row[0].strip(),
                                'name': row[1].strip(),
                                'close': float(row[2].replace(',', '')) if row[2].strip() not in ['-', ''] else 0,
                                'turnover': float(row[3].replace(',', '')) if row[3].strip() not in ['-', ''] else 0,
                                'seal_amount': float(row[4].replace(',', '').replace('-', '0')) if row[4].strip() not in ['-', ''] else 0,
                                'seal_fund': float(row[5].replace(',', '').replace('-', '0')) if row[5].strip() not in ['-', ''] else 0,
                                'industry': row[6].strip() if len(row) > 6 else '',
                            }
                            if stock['code'].isdigit() and len(stock['code']) == 6:
                                all_stocks.append(stock)
                        except (ValueError, IndexError):
                            pass
        elif pw_result.get('text'):
            # 备用：纯文本解析
            text = pw_result['text']
            idx = text.find('涨停股一览')
            if idx >= 0:
                table_text = text[idx:idx+10000]
                parsed = parse_zt_stock_table(table_text)
                print(f"      → 纯文本解析: {len(parsed)} 行数据")
                all_stocks.extend(parsed)
        else:
            print(f"      → 无数据: {pw_result.get('error', 'unknown')[:100]}")

        _safe_delay(3)

    # === 4. 去重合并 ===
    seen = set()
    unique_stocks = []
    for s in all_stocks:
        key = s['code']
        if key not in seen:
            seen.add(key)
            unique_stocks.append(s)

    # 按封单资金排序
    unique_stocks.sort(key=lambda x: x['seal_fund'], reverse=True)

    results['涨停股详细列表'] = unique_stocks
    print(f"\n  合计去重后: {len(unique_stocks)} 只涨停股")

    # === 5. 打印关键数据 ===
    print(f"\n{'='*50}")
    print(f"{date_str} 涨停复盘数据摘要")
    print(f"{'='*50}")

    if results['午间涨停复盘']:
        wj = results['午间涨停复盘']
        print(f"\n【午间涨停复盘】{wj['title']}")
        parsed = parse_ztfp_summary(wj['full_text'])
        wj['summary'] = parsed
        for k, v in parsed.items():
            print(f"  {k}: {v}")

    if results['收盘涨停复盘']:
        sb = results['收盘涨停复盘']
        print(f"\n【收盘涨停复盘】{sb['title']}")
        parsed = parse_ztfp_summary(sb['full_text'])
        sb['summary'] = parsed
        for k, v in parsed.items():
            print(f"  {k}: {v}")

    if unique_stocks:
        print(f"\n【涨停股详细列表】共 {len(unique_stocks)} 只")
        print(f"\n  封单资金 TOP10:")
        for s in unique_stocks[:10]:
            print(f"    {s['code']} {s['name']:8s} 收盘{s['close']:8.2f} 封单{s['seal_amount']:10.1f}万股 封单资金{s['seal_fund']:12.1f}万 {s['industry']}")

    return results


def save_to_excel(data, out_path):
    """将涨停股详细数据保存为Excel"""
    try:
        import pandas as pd
    except ImportError:
        print("pandas not available, skipping Excel export")
        return

    stocks = data.get('涨停股详细列表', [])
    if not stocks:
        print("No stock data to export")
        return

    df = pd.DataFrame(stocks)
    df = df.sort_values('seal_fund', ascending=False)

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        # Sheet1: 按封单资金排序
        df.to_excel(writer, sheet_name='封单资金排序', index=False)

        # Sheet2: 按行业分组
        industry_df = df.groupby('industry').agg({
            'code': 'count',
            'seal_fund': 'sum',
            'close': 'mean'
        }).rename(columns={'code': '涨停数量', 'seal_fund': '总封单资金', 'close': '平均收盘价'})
        industry_df = industry_df.sort_values('涨停数量', ascending=False)
        industry_df.to_excel(writer, sheet_name='按行业统计')

        # Sheet3: 完整摘要
        summary_data = []
        if data.get('午间涨停复盘'):
            sb = data['午间涨停复盘']
            summary_data.append(['午间涨停复盘', sb['title'], sb.get('media', ''), sb['date']])
            for k, v in sb.get('summary', {}).items():
                summary_data.append(['', k, v, ''])
        if data.get('收盘涨停复盘'):
            sb = data['收盘涨停复盘']
            summary_data.append(['收盘涨停复盘', sb['title'], sb.get('media', ''), sb['date']])
            for k, v in sb.get('summary', {}).items():
                summary_data.append(['', k, v, ''])

        summary_df = pd.DataFrame(summary_data, columns=['类型', '标题/指标', '数值/来源', '日期'])
        summary_df.to_excel(writer, sheet_name='复盘摘要', index=False)

    print(f"\nExcel已保存: {out_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='涨停复盘完整数据采集')
    parser.add_argument('--date', '-d', type=str, default=None,
                        help='日期 YYYY-MM-DD，默认今天')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='输出目录，默认 /home/admin/stock_knowledge/reports/')
    parser.add_argument('--skip-excel', '-e', action='store_true',
                        help='跳过Excel导出')
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime('%Y-%m-%d')
    out_dir = args.output or '/home/admin/stock_knowledge/reports'
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"采集 {date_str} 涨停复盘完整数据")
    print(f"{'='*50}")

    # 采集数据
    data = collect_ztfp_full(date_str)

    # 保存JSON
    date_clean = date_str.replace('-', '')
    json_path = f'{out_dir}/涨停复盘_完整_{date_clean}.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nJSON已保存: {json_path}")

    # 保存Excel
    if not args.skip_excel:
        excel_path = f'{out_dir}/涨停复盘_完整_{date_clean}.xlsx'
        try:
            save_to_excel(data, excel_path)
        except Exception as e:
            print(f"Excel导出失败: {e}")

    return data


if __name__ == '__main__':
    main()
