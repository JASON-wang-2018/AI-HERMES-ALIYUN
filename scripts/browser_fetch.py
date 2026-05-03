#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 浏览器数据采集模块
作为 AKShare/Baostock/Tushare 的补充，用于抓取动态JS页面
防封策略：随机延时 + 请求间隔 + 单浏览器复用

Author: 纳福 for Jason

依赖安装（已有venv）:
  cd ~/stock_knowledge && source .venv/bin/activate
  uv add playwright && playwright install chromium
"""

import time
import random
import sqlite3
import os
import re
from datetime import datetime
from pathlib import Path

# 全局浏览器单例
_browser = None          # Browser实例
_playwright = None       # Playwright实例（with上下文进入后的对象）
_playwright_ctx = None   # sync_playwright() 上下文管理器本身

BASE_DIR = Path("~/stock_knowledge").expanduser()
DB_PATH = BASE_DIR / "database/stock_data.db"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [Browser] {msg}")
    log_file = LOG_DIR / "browser_fetch.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] [Browser] {msg}\n")


# ===================== Playwright 初始化（单例） =====================

def _init_browser():
    """初始化浏览器单例（仅在真正需要时才启动）"""
    global _browser, _playwright, _playwright_ctx

    if _browser is not None:
        try:
            if _browser.is_connected():
                return _browser
        except Exception:
            pass

    # 清理旧引用
    _browser = None
    _playwright = None
    _playwright_ctx = None

    from playwright.sync_api import sync_playwright
    _playwright_ctx = sync_playwright()
    _playwright = _playwright_ctx.__enter__()
    _browser = _playwright.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-blink-features=AutomationControlled',
            '--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
    )
    log("浏览器启动成功（headless）")
    return _browser


def _new_page():
    """创建新页面（每次采集独立页面，防止状态污染）"""
    browser = _init_browser()
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    return page


def close_browser():
    """关闭浏览器（全局清理）"""
    global _browser, _playwright, _playwright_ctx

    if _browser:
        try:
            _browser.close()
        except Exception:
            pass
        _browser = None

    if _playwright_ctx:
        try:
            _playwright_ctx.__exit__(None, None, None)
        except Exception:
            pass
        _playwright_ctx = None

    _playwright = None
    log("浏览器已关闭")


def _random_delay_between_requests():
    """请求间随机延时（3~8秒，防止固定频率被识别）"""
    t = random.uniform(3.0, 8.0)
    time.sleep(t)


# ===================== 通用采集函数 =====================

def fetch_page_content(url, wait_selector=None, wait_time=3, timeout=20000):
    """
    通用页面采集（支持JS渲染）

    Args:
        url: 目标URL
        wait_selector: 等待某个CSS选择器出现（可选）
        wait_time: 额外等待秒数（默认3秒，等JS渲染）
        timeout: 超时毫秒

    Returns:
        dict: {"html": str, "title": str, "url": str}
    """
    page = None
    try:
        page = _new_page()
        _random_delay_between_requests()

        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        time.sleep(wait_time)

        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=timeout // 2)
            except Exception:
                pass

        html = page.content()
        title = page.title()

        return {"html": html, "title": title, "url": url}

    except Exception as e:
        log(f"采集失败 [{url}]: {e}")
        return {"html": "", "title": "", "url": url, "error": str(e)}

    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


def fetch_and_screenshot(url, screenshot_path, wait_time=3, timeout=20000):
    """采集页面并截图（用于人工复核/视觉验证）"""
    page = None
    try:
        page = _new_page()
        _random_delay_between_requests()

        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        time.sleep(wait_time)
        page.screenshot(path=screenshot_path, full_page=False)

        title = page.title()
        log(f"截图成功: {screenshot_path} - {title}")
        return True

    except Exception as e:
        log(f"截图失败 [{url}]: {e}")
        return False

    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


# ===================== 财经网站专项采集 =====================

def fetch_eastmoney_board(wait_time=5):
    """
    东方财富板块行情（行业/概念板块列表，JS渲染）
    用途：替代 akshare.stock_fund_flow_industry() 的备选方案
    """
    url = "https://quote.eastmoney.com/center/boardlist.html#industry_board"
    result = fetch_page_content(url, wait_selector="table", wait_time=wait_time)

    if not result.get("html"):
        return []

    stocks = []
    try:
        text = result["html"]
        pattern = r'"boardName"\s*:\s*"([^"]+)".*?"priceChangeRate"\s*:\s*"([^"]+)"'
        matches = re.findall(pattern, text, re.S)
        for name, pct in matches[:50]:
            stocks.append({
                "name": name.strip(),
                "pct": pct.strip(),
                "source": "eastmoney_board"
            })
    except Exception as e:
        log(f"解析东财板块数据失败: {e}")

    log(f"东财板块数据: 获取 {len(stocks)} 条")
    return stocks


def fetch_ths_fupan(wait_time=5):
    """
    同花顺复盘页（涨停/跌停/炸板等数据，JS渲染）
    用途：替代人工复盘采集
    """
    url = "https://stock.10jqka.com.cn/fupan/"
    result = fetch_page_content(url, wait_selector="table", wait_time=wait_time)

    if result.get("error"):
        log(f"同花顺复盘页采集失败: {result['error']}")
        return {}

    log(f"同花顺复盘页采集成功: {result['title']}")
    return {
        "title": result["title"],
        "url": result["url"],
        "html_preview": result["html"][:3000],
        "source": "ths_fupan"
    }


def fetch_xueqiu_stock(stock_code, wait_time=5):
    """
    雪球个股页面（资金流/股东/公告等，需登录数据）
    用处：获取个股深度信息
    """
    prefix = "SH" if stock_code.startswith("6") else "SZ"
    url = f"https://xueqiu.com/S/{prefix}{stock_code}"
    result = fetch_page_content(url, wait_selector=".stock-info", wait_time=wait_time)

    if result.get("error"):
        log(f"雪球 [{stock_code}]: {result['error']}")
        return {}

    log(f"雪球 [{stock_code}]: {result['title']}")
    return {
        "stock_code": stock_code,
        "title": result["title"],
        "html_preview": result["html"][:1500],
        "source": "xueqiu"
    }


def fetch_eastmoney_realtime(stock_code, wait_time=4):
    """
    东方财富个股实时行情（动态页面，包含盘口数据）
    用途：获取分价表、买卖盘口等 AKShare 难以获取的数据
    """
    secid = f"{'1' if stock_code.startswith('6') else '0'}.{stock_code}"
    url = f"https://quote.eastmoney.com/concept/{secid}.html"
    result = fetch_page_content(url, wait_selector=".quote-info", wait_time=wait_time)

    if result.get("error"):
        log(f"东财实时 [{stock_code}]: {result['error']}")
        return {}

    return {
        "stock_code": stock_code,
        "title": result["title"],
        "html_preview": result["html"][:2000],
        "source": "eastmoney_realtime"
    }


def fetch_sina_stock(stock_code, wait_time=3):
    """
    新浪财经个股页面（动态内容：实时价格/资金流向）
    """
    symbol = f"{'sh' if stock_code.startswith('6') else 'sz'}{stock_code}"
    url = f"https://finance.sina.com.cn/realstock/company/{symbol}/nc.shtml"
    result = fetch_page_content(url, wait_selector=".price", wait_time=wait_time)

    if result.get("error"):
        log(f"新浪 [{stock_code}]: {result['error']}")
        return {}

    return {
        "stock_code": stock_code,
        "title": result["title"],
        "html_preview": result["html"][:2000],
        "source": "sina"
    }


# ===================== 数据保存 =====================

def save_browser_fetch_log(data, page_type, stock_code=""):
    """记录浏览器采集日志到数据库"""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS browser_fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT,
                page_type TEXT,
                title TEXT,
                url TEXT,
                fetch_time TEXT,
                html_preview TEXT
            )
        """)
        conn.execute("""
            INSERT INTO browser_fetch_log
            (stock_code, page_type, title, url, fetch_time, html_preview)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            stock_code,
            page_type,
            data.get("title", ""),
            data.get("url", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get("html_preview", "")[:500]
        ))
        conn.commit()
    except Exception as e:
        log(f"数据库记录失败: {e}")
    finally:
        conn.close()


# ===================== 主动关闭浏览器 =====================

import atexit
def _cleanup():
    close_browser()
atexit.register(_cleanup)


# ===================== 演示/测试 =====================

if __name__ == "__main__":
    print("=" * 50)
    print("Playwright 浏览器采集测试")
    print("=" * 50)

    screenshot_dir = LOG_DIR / "browser_screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    # 测试1: 同花顺复盘页截图
    print("\n[测试1] 同花顺复盘页截图...")
    ok = fetch_and_screenshot(
        "https://stock.10jqka.com.cn/fupan/",
        str(screenshot_dir / "ths_fupan_test.png"),
        wait_time=5
    )
    print(f"  结果: {'✅ 成功' if ok else '❌ 失败'}")

    # 测试2: 新浪财经个股页
    print("\n[测试2] 新浪财经 600351 截图...")
    ok = fetch_and_screenshot(
        "https://finance.sina.com.cn/realstock/company/sh600351/nc.shtml",
        str(screenshot_dir / "sina_600351_test.png"),
        wait_time=4
    )
    print(f"  结果: {'✅ 成功' if ok else '❌ 失败'}")

    # 测试3: 东财板块数据
    print("\n[测试3] 东财板块数据采集...")
    boards = fetch_eastmoney_board(wait_time=5)
    print(f"  获取板块数: {len(boards)}")
    if boards:
        print(f"  示例: {boards[0]}")

    # 测试4: 雪球个股页
    print("\n[测试4] 雪球个股页 600351...")
    xq = fetch_xueqiu_stock("600351", wait_time=5)
    print(f"  标题: {xq.get('title', 'N/A')}")

    # 最终清理
    print("\n[清理] 关闭浏览器...")
    close_browser()

    print("\n✅ 全部测试完成！")
    print(f"截图目录: {screenshot_dir}")
