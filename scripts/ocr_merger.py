#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR涨停数据 + AKShare 数据合并流水线
功能：
  1. 用 RapidOCR 识别韭研公社图片 → 提取股票名称、代码、成交额、流通市值、涨停时间、题材关键词
  2. 拉取 AKShare 实时涨跌停池 → 提取封板资金、连板数、换手率等
  3. 两个数据源按"代码+名称"匹配合并，输出完整的涨停复盘数据

使用：
  python3 scripts/ocr_merger.py 20260427
  python3 scripts/ocr_merger.py 20260427 /path/to/image.jpg
"""

import sys
import re
import json
import sqlite3
from datetime import datetime
from rapidocr_onnxruntime import RapidOCR
import akshare as ak
import pandas as pd


# ============================================================
# 第一步：OCR 识别图片
# ============================================================

def ocr_image(image_path: str) -> dict:
    """
    用 RapidOCR 识别涨停复盘图片
    返回结构化数据（股票列表 + 全局汇总）

    策略：
      1. 识别所有股票行（代码.交易所 代码 名称）
      2. 识别所有题材标签行（X天Y板 / 关键词*数字 / 关键词+关键词...）
      3. 题材标签只归属"上一个出现的股票"，不用行号位置强关联
      4. OCR识别有误差，用名称模糊匹配兜底
    """
    ocr = RapidOCR()
    result, _ = ocr(image_path)
    if not result:
        return {"stocks": [], "header": {}}

    # ---- 1. 提取所有题材标签行 ----
    # 格式：X天Y板 / 关键词*数字 / 关键词+关键词+...
    theme_lines = []
    for line in result:
        text = line[1].strip()
        conf = line[2]
        # 题材组标题（如 "算力*7"、"国产芯片*6"、"机器人*6"）
        if re.match(r'^[\u4e00-\u9fa5]+\*[\d]+$', text) or \
           re.match(r'^[\u4e00-\u9fa5*a-zA-Z0-9（）()（）《》]+[\+×][\u4e00-\u9fa5*a-zA-Z0-9]+', text) or \
           '天' in text and '板' in text:  # X天Y板
            theme_lines.append({"text": text, "conf": conf, "type": "banner"})
        # 个股题材关键词行（包含+或×分隔的多个词）
        elif re.search(r'[\u4e00-\u9fa5]+[\+×][\u4e00-\u9fa5]+', text) and len(text) > 4:
            theme_lines.append({"text": text, "conf": conf, "type": "keywords"})
        elif '涨停关键词' in text:
            clean = text.replace('涨停关键词', '').strip()
            if clean:
                theme_lines.append({"text": clean, "conf": conf, "type": "keywords"})

    # ---- 2. 提取所有股票行 ----
    stock_rows = []
    for line in result:
        text = line[1].strip()
        conf = line[2]
        code_match = re.search(r'(\d{6})\.(SH|SZ)', text)
        if code_match:
            code = code_match.group(1)
            market = 'SH' if code_match.group(2) == 'SH' else 'SZ'
            # 名称 = 代码后面的文字
            name_part = re.sub(r'\d{6}\.(SH|SZ)', '', text).strip()
            # 去掉数字（成交额等）
            name_part = re.sub(r'[\d\.]+$', '', name_part).strip()

            row = {
                "代码": code,
                "市场": market,
                "名称": name_part,
                "置信度": conf,
                "成交额亿": None,
                "流通市值亿": None,
                "封板时间": None,
                "板数描述": None,
                "题材": None,
            }

            # 从同行提取数字（成交额/市值候选）
            nums = re.findall(r'(\d+\.\d+)', text)
            if nums:
                row["成交额亿"] = float(nums[-1])

            stock_rows.append(row)

    # ---- 3. 建立"当前题材"状态，分配给后续股票 ----
    current_theme = None
    current_board = None

    for item in theme_lines:
        text = item["text"]
        # X天Y板 格式
        board_match = re.search(r'(\d+天\d+板|\d+天\d*板|\d+板)', text)
        if board_match:
            current_board = board_match.group(1)

    # 把题材分配给股票（题材行出现在股票之前的，归属该股票）
    # 遍历OCR行，维护当前活跃的题材列表
    active_themes = []  # 当前积累的题材标签

    for item in theme_lines:
        text = item["text"]
        if item["type"] == "banner":
            # 把banner标题（如"算力*7"）转为纯词
            clean = re.sub(r'\*[\d]+$', '', text)
            if clean:
                active_themes.append(clean)
        elif item["type"] in ("keywords",):
            # 去掉X天Y板描述，保留纯题材
            clean = re.sub(r'\d+天\d*板', '', text)
            clean = re.sub(r'\d+板', '', clean).strip()
            if clean and len(clean) > 1:
                active_themes.append(clean)

    # 现在把active_themes分配给最后一个股票
    if active_themes and stock_rows:
        # 取最后一个有题材的
        theme_str = "+".join(active_themes[-5:])  # 最近5个题材
        if stock_rows:
            stock_rows[-1]["题材"] = theme_str

    # 再次扫描：把板数描述和题材分配给最近的股票
    # 用股票行在result中的位置来关联
    stock_indices = {}  # code → result中的index
    for i, line in enumerate(result):
        for sr in stock_rows:
            if str(sr["代码"]) in line[1]:
                sr["_result_idx"] = i
                break

    # 对每只股票，从它的位置往后找最近的题材/板数行
    for sr in stock_rows:
        code = sr["代码"]
        pos = sr.get("_result_idx", 0)

        # 找后面3行内的板数描述
        for j in range(pos, min(pos + 4, len(result))):
            text = result[j][1]
            board_m = re.search(r'(\d+天\d+板|\d+板)', text)
            if board_m and not sr.get("板数描述"):
                sr["板数描述"] = board_m.group(1)
                break

        # 找后面5行内的题材关键词
        for j in range(pos, min(pos + 6, len(result))):
            text = result[j][1]
            if text == sr.get("名称", ""):
                continue
            # 题材行特征：有+或×连接多个词
            if re.search(r'[\u4e00-\u9fa5]+[\+×][\u4e00-\u9fa5]+', text) and len(text) > 4:
                # 去掉X天Y板
                clean = re.sub(r'\d+天\d*板', '', text)
                clean = re.sub(r'\d+板', '', clean).strip()
                if clean and len(clean) > 2:
                    sr["题材"] = clean
                    break

    # ---- 4. 提取汇总信息 ----
    header = {}
    for line in result:
        text = line[1]
        if '涨停' in text and '破板率' in text:
            zt = re.search(r'涨停(\d+)家', text)
            dt = re.search(r'跌停(\d+)家', text)
            lb = re.search(r'连板(\d+)家', text)
            pb = re.search(r'破板率([\d.]+)%', text)
            if zt: header['涨停家数'] = int(zt.group(1))
            if dt: header['跌停家数'] = int(dt.group(1))
            if lb: header['连板家数'] = int(lb.group(1))
            if pb: header['破板率'] = float(pb.group(1))
            break

    return {"stocks": stock_rows, "header": header}


# ============================================================
# 第二步：拉取 AKShare 实时数据
# ============================================================

def fetch_akshare(date: str) -> dict:
    """
    拉取 AKShare 涨跌停池数据
    """
    try:
        zt = ak.stock_zt_pool_em(date=date)
        dt = ak.stock_zt_pool_dtgc_em(date=date)
        zbgc = ak.stock_zt_pool_zbgc_em(date=date)
    except Exception as e:
        return {"error": str(e)}

    return {
        "zt": zt,
        "dt": dt,
        "zbgc": zbgc,
        "zt_count": len(zt),
        "dt_count": len(dt),
        "zbgc_count": len(zbgc) if zbgc is not None and len(zbgc) > 0 else 0,
    }


# ============================================================
# 第三步：合并两个数据源
# ============================================================

def merge_data(ocr_data: dict, akshare_data: dict) -> pd.DataFrame:
    """
    按"代码+名称"匹配合并
    AKShare提供：封板资金、连板数、换手率、行业、炸板次数
    OCR提供：题材标签、成交额（完整）、流通市值、板数描述
    """
    zt = akshare_data.get("zt", pd.DataFrame())
    if len(zt) == 0:
        return pd.DataFrame()

    # 标准化AKShare的代码（去掉.SH/.SZ后缀用于匹配）
    zt["代码纯"] = zt["代码"].str.replace(r'\.SH|\.SZ', '', regex=True)

    # 标准化OCR数据
    ocr_stocks = ocr_data.get("stocks", [])
    for s in ocr_stocks:
        if "代码" in s:
            s["代码纯"] = s["代码"]

    # 建立代码→OCR数据的映射
    ocr_map = {}
    for s in ocr_stocks:
        if "代码纯" in s:
            ocr_map[s["代码纯"]] = s

    merged_rows = []
    for _, row in zt.iterrows():
        code = row["代码纯"]
        new_row = row.to_dict()

        if code in ocr_map:
            ocr_s = ocr_map[code]
            # 补充OCR数据
            if "名称" in ocr_s: new_row["OCR名称"] = ocr_s["名称"]
            if "题材" in ocr_s: new_row["题材标签"] = ocr_s["题材"]
            if "封板时间" in ocr_s: new_row["OCR封板时间"] = ocr_s["封板时间"]
            if "板数描述" in ocr_s: new_row["板数描述"] = ocr_s["板数描述"]
            # 成交额/流通市值以OCR为准（更完整）
            if "成交额亿" in ocr_s: new_row["成交额亿_ocr"] = ocr_s["成交额亿"]
            if "流通市值亿" in ocr_s: new_row["流通市值亿_ocr"] = ocr_s["流通市值亿"]
            ocr_s["_matched"] = True
        else:
            new_row["OCR名称"] = None
            new_row["题材标签"] = None
            new_row["OCR封板时间"] = None
            new_row["板数描述"] = None

        merged_rows.append(new_row)

    # 检查OCR中未匹配到的（AKShare没有涨停的，但图片里有）
    unmatched = [s for s in ocr_stocks if not s.get("_matched", False)]
    if unmatched:
        print(f"  ⚠️ OCR中有 {len(unmatched)} 只股不在AKShare涨停池中")

    result = pd.DataFrame(merged_rows)
    return result


# ============================================================
# 第四步：题材聚合 + 龙头分析
# ============================================================

def analyze_sectors(df: pd.DataFrame) -> dict:
    """
    基于合并数据做题材强度分析
    """
    if len(df) == 0:
        return {}

    # 从题材标签聚合
    theme_stocks = {}
    for _, row in df.iterrows():
        tags = row.get("题材标签", "")
        if not tags or pd.isna(tags):
            # 用AKShare行业作为兜底
            tags = str(row.get("所属行业", ""))
        if tags:
            keywords = re.split(r'[+×*]', str(tags))
            for kw in keywords:
                kw = kw.strip()
                if kw and len(kw) >= 2:
                    if kw not in theme_stocks:
                        theme_stocks[kw] = []
                    theme_stocks[kw].append({
                        "名称": row.get("OCR名称") or row.get("名称"),
                        "代码": row.get("代码"),
                        "连板": row.get("板数描述") or f"{row.get('连板数', 1)}板",
                    })

    # 统计每个题材的涨停家数
    theme_stats = []
    for kw, stocks in theme_stocks.items():
        theme_stats.append({
            "题材": kw,
            "涨停数": len(stocks),
            "代表股": [s["名称"] for s in stocks[:3]],
        })

    theme_stats.sort(key=lambda x: -x["涨停数"])
    return theme_stats


def format_report(df: pd.DataFrame, ocr_header: dict, date: str) -> str:
    """生成完整的复盘报告"""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"📋 涨停复盘报告 | {date} | OCR+AKShare 合并版")
    lines.append(f"{'='*60}")

    # 情绪总览
    if ocr_header:
        lines.append(f"\n🌡️ 情绪总览（OCR）：")
        for k, v in ocr_header.items():
            lines.append(f"  {k}: {v}")
    elif len(df) > 0:
        lines.append(f"\n🌡️ 情绪总览（AKShare）：")
        lines.append(f"  涨停: {len(df)}家")

    # 题材强度
    theme_stats = analyze_sectors(df)
    if theme_stats:
        lines.append(f"\n📈 题材强度 Top10（基于OCR概念标签）：")
        medals = ["🥇", "🥈", "🥉"]
        for i, t in enumerate(theme_stats[:10]):
            medal = medals[i] if i < 3 else f" {i+1} "
            reps = "、".join([str(x) for x in t["代表股"]])
            lines.append(f"  {medal} {t['题材']}: {t['涨停数']}家 → {reps}")

    # 核心连板股
    if len(df) > 0:
        lianban = df[df["连板数"] >= 2].sort_values("连板数", ascending=False)
        if len(lianban) > 0:
            lines.append(f"\n🔥 核心连板股：")
            for _, r in lianban.head(10).iterrows():
                name = r.get("OCR名称") or r.get("名称", "?")
                code = r.get("代码", "?")
                board = r.get("板数描述") or f"{int(r.get('连板数', 0))}板"
                theme = r.get("题材标签", r.get("所属行业", ""))
                fengdan = r.get("封板资金", 0)
                f_str = f"{fengdan/1e8:.1f}亿" if fengdan > 1e8 else f"{fengdan/1e4:.0f}万"
                lines.append(f"  {name}({code}) {board} | 封单:{f_str} | {theme}")

    # 详细涨停表
    lines.append(f"\n{'='*60}")
    lines.append(f"📊 涨停股详细数据（共{len(df)}家）")
    lines.append(f"{'='*60}")

    # 排序：先按连板数，再按成交额
    df_sorted = df.sort_values(["连板数", "成交额"], ascending=[False, False])

    cols = ["代码", "名称", "连板数", "所属行业", "题材标签", "换手率", "封板资金", "首次封板时间"]
    available = [c for c in cols if c in df_sorted.columns]
    # 截取前20行
    display = df_sorted[available].head(20).copy()
    display["封板资金_亿"] = display["封板资金"].apply(
        lambda x: f"{x/1e8:.1f}亿" if x > 1e8 else (f"{x/1e4:.0f}万" if x > 0 else "0")
    )
    display["换手率_"] = display["换手率"].apply(lambda x: f"{x:.1f}%")
    for _, r in display.iterrows():
        theme = str(r.get("题材标签", ""))[:30] if pd.notna(r.get("题材标签")) else ""
        sector = r.get("所属行业", "")
        name = str(r.get("名称", ""))
        code = str(r.get("代码", ""))
        board = int(r.get("连板数", 0))
        f_str = r.get("封板资金_亿", "?")
        hs = r.get("换手率_", "?")
        lines.append(f"  {name}({code}) {board}板 | {sector} | {theme} | 封单:{f_str} | 换手:{hs}")

    return "\n".join(lines)


# ============================================================
# 第五步：存入 SQLite
# ============================================================

def save_to_db(df: pd.DataFrame, date: str, ocr_header: dict):
    """保存到数据库"""
    conn = sqlite3.connect("/home/admin/stock_knowledge/database/stock_data.db")
    cursor = conn.cursor()

    # 建表（如果不存在）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zt_review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            code TEXT,
            name TEXT,
            board_desc TEXT,
            sector TEXT,
            theme TEXT,
            turnover_rate REAL,
            fengdan_wan REAL,
            first_seal_time TEXT,
           成交额亿 REAL,
            流通市值亿 REAL,
            source TEXT,
            UNIQUE(date, code)
        )
    """)

    for _, row in df.iterrows():
        code = str(row.get("代码", "")).replace(".SH", "").replace(".SZ", "")
        name = str(row.get("OCR名称") or row.get("名称", ""))
        board_desc = str(row.get("板数描述") or f"{int(row.get('连板数', 1))}板")
        sector = str(row.get("所属行业", ""))
        theme = str(row.get("题材标签", "")) if pd.notna(row.get("题材标签")) else ""
        turnover = float(row.get("换手率", 0)) if pd.notna(row.get("换手率")) else 0
        fengdan = float(row.get("封板资金", 0)) if pd.notna(row.get("封板资金")) else 0
        seal_time = str(row.get("首次封板时间", ""))
        amount = float(row.get("成交额亿_ocr", 0)) if pd.notna(row.get("成交额亿_ocr")) else 0
        mcap = float(row.get("流通市值亿_ocr", 0)) if pd.notna(row.get("流通市值亿_ocr")) else 0

        cursor.execute("""
            INSERT OR REPLACE INTO zt_review
            (date, code, name, board_desc, sector, theme, turnover_rate,
             fengdan_wan, first_seal_time, 成交额亿, 流通市值亿, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, code, name, board_desc, sector, theme, turnover,
              fengdan / 1e4, seal_time, amount, mcap, "OCR+AKShare"))

    conn.commit()
    conn.close()
    print(f"  ✅ 已存入SQLite: {len(df)}条记录")


# ============================================================
# 四大指数日线
# ============================================================

def save_index_data(date: str):
    """拉取并保存四大指数收盘数据"""
    indices = [
        ("上证指数", "sh000001"),
        ("沪深300", "sh000300"),
        ("深证成指", "sz399001"),
        ("创业板指", "sz399006"),
    ]

    conn = sqlite3.connect("/home/admin/stock_knowledge/database/stock_data.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS index_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            index_name TEXT,
            close REAL,
            change REAL,
            change_pct REAL,
            volume亿 REAL,
            UNIQUE(date, index_name)
        )
    """)

    for name, symbol in indices:
        df = ak.stock_zh_index_daily(symbol=symbol)
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        row = df[df['date'] == date]
        if len(row) == 0:
            print(f"  {name}: {date} 无数据（可能非交易日）")
            continue
        cur = row.iloc[0]
        prev_df = df[df['date'] < date]
        if len(prev_df) == 0:
            continue
        prev = prev_df.iloc[-1]

        change = cur['close'] - prev['close']
        change_pct = change / prev['close'] * 100
        volume亿 = cur['volume'] / 1e8

        cursor.execute("""
            INSERT OR REPLACE INTO index_daily
            (date, index_name, close, change, change_pct, volume亿)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, name, cur['close'], change, change_pct, volume亿))

        arrow = "up" if change >= 0 else "down"
        print(f"  {name}: {cur['close']:.2f} {arrow} {change_pct:+.2f}% vol {volume亿:.0f}亿")

    conn.commit()
    conn.close()


# ============================================================
# 主流程
# ============================================================

def main():
    args = sys.argv
    if len(args) < 2:
        date = (datetime.now() - pd.Timedelta(days=1)).strftime("%Y%m%d")
    else:
        date = args[1]

    # 格式化日期
    date_display = f"{date[:4]}-{date[4:6]}-{date[6:]}"

    # 图片路径
    if len(args) >= 3:
        image_path = args[2]
    else:
        # 尝试从image_cache找最新图片
        import glob
        cache_files = sorted(glob.glob("/home/admin/.hermes/image_cache/img_*.jpg"))
        image_path = cache_files[-1] if cache_files else None

    print(f"\n📡 开始处理: {date_display}")
    if image_path:
        print(f"  📷 图片: {image_path}")

    # ---- OCR ----
    ocr_data = {"stocks": [], "header": {}}
    if image_path:
        print("  🔍 OCR识别中...")
        ocr_data = ocr_image(image_path)
        print(f"  OCR结果: {len(ocr_data['stocks'])}只股票识别成功")
        if ocr_data.get("header"):
            print(f"  OCR汇总: {ocr_data['header']}")

    # ---- AKShare ----
    print("  📊 拉取AKShare数据...")
    akshare_data = fetch_akshare(date)
    if "error" in akshare_data:
        print(f"  ❌ AKShare错误: {akshare_data['error']}")
        return

    zt_count = akshare_data["zt_count"]
    print(f"  AKShare涨停池: {zt_count}家")

    # ---- 合并 ----
    print("  🔗 合并数据...")
    merged_df = merge_data(ocr_data, akshare_data)
    print(f"  合并完成: {len(merged_df)}条")

    # ---- 报告 ----
    report = format_report(merged_df, ocr_data.get("header", {}), date_display)
    print(report)

    # ---- 存库 ----
    if len(merged_df) > 0:
        save_to_db(merged_df, date_display, ocr_data.get("header", {}))

    # ---- 顺便拉四大指数 ----
    save_index_data(date_display)




if __name__ == "__main__":
    main()
