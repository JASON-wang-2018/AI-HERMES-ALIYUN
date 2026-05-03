#!/usr/bin/env python3
"""
每日18:00 股市综合报告
- 读取午评+收评（12:45 & 17:15入库）
- 采集东财指数+板块数据
- 生成综合行情报告
"""
import sqlite3, json, subprocess, re, os
from datetime import datetime, timezone, timedelta
from typing import Optional

DB_PATH = os.path.expanduser("~/stock_knowledge/database/daily_market.db")
TZ_CST = timezone(timedelta(hours=8))

# ── 数据库初始化 ──────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            index_code TEXT NOT NULL,
            index_name TEXT NOT NULL,
            price REAL,
            pct_chg REAL,
            volume REAL,
            amount REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, index_code)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_sector (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            sector_code TEXT NOT NULL,
            sector_name TEXT NOT NULL,
            pct_chg REAL,
            lead_stock TEXT,
            amount REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, sector_code)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            review_type TEXT NOT NULL CHECK(review_type IN ('午评','收评')),
            title TEXT,
            content TEXT,
            key_points TEXT,
            report_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, review_type)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT UNIQUE NOT NULL,
            report_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_index_date ON daily_index(trade_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sector_date ON daily_sector(trade_date)")
    conn.commit()
    conn.close()

# ── curl抓取工具 ──────────────────────────────────────────
def curl_json(url: str) -> dict:
    cmd = [
        "curl", "-s", "-L", url,
        "-H", "Referer: https://quote.eastmoney.com/",
        "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout)

# ── 数据采集 ───────────────────────────────────────────────
def fetch_major_indices(trade_date: str) -> list:
    url = (
        "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        "?fields=f1,f2,f3,f12,f14&"
        "secids=1.000001,0.399001,0.399006,1.000688,0.899050,1.001268"
        "&ut=fa5fd1943c7b386f172d6893dbfba10b&fltt=2&invt=2"
    )
    data = curl_json(url).get("data", {}).get("diff", [])
    rows = []
    for item in data:
        code = str(item.get("f12", ""))
        name = item.get("f14", "")
        price = item.get("f2", 0)
        pct = item.get("f3", 0)
        rows.append({
            "trade_date": trade_date,
            "index_code": code,
            "index_name": name,
            "price": price if price != "-" else None,
            "pct_chg": pct if pct != "-" else None,
            "volume": None, "amount": None
        })
    return rows

def fetch_top_sectors(trade_date: str, limit: int = 30) -> list:
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={limit}&po=1&np=1"
        "&ut=fa5fd1943c7b386f172d6893dbfba10b"
        "&fltt=2&invt=2&fid=f3&fs=m:90+t:2"
        "&fields=f12,f14,f3,f8,f6"
    )
    data = curl_json(url).get("data", {}).get("diff", [])
    rows = []
    for item in data:
        rows.append({
            "trade_date": trade_date,
            "sector_code": str(item.get("f12", "")),
            "sector_name": item.get("f14", ""),
            "pct_chg": item.get("f3", 0),
            "lead_stock": item.get("f8", ""),
            "amount": item.get("f6", 0)
        })
    return rows

# ── 入库 ───────────────────────────────────────────────────
def save_to_db(indices: list, sectors: list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for row in indices:
        c.execute("""
            INSERT OR REPLACE INTO daily_index
            (trade_date,index_code,index_name,price,pct_chg,volume,amount)
            VALUES (?,?,?,?,?,?,?)
        """, (row["trade_date"],row["index_code"],row["index_name"],
              row["price"],row["pct_chg"],row["volume"],row["amount"]))
    for row in sectors:
        c.execute("""
            INSERT OR REPLACE INTO daily_sector
            (trade_date,sector_code,sector_name,pct_chg,lead_stock,amount)
            VALUES (?,?,?,?,?,?)
        """, (row["trade_date"],row["sector_code"],row["sector_name"],
              row["pct_chg"],row["lead_stock"],row["amount"]))
    conn.commit()
    conn.close()

# ── 读取午评/收评 ─────────────────────────────────────────
def get_reviews(trade_date: str) -> dict:
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT review_type, title, content, key_points, report_text
        FROM daily_review WHERE trade_date=?
    """, (trade_date,))
    rows = c.fetchall()
    conn.close()
    result = {}
    for rtype, title, content, key_points_str, report_text in rows:
        # key_points 可能是JSON dict或旧版纯字符串
        try:
            kp = json.loads(key_points_str) if key_points_str else {}
        except:
            kp = {"raw_points": key_points_str or ""}
        result[rtype] = {
            "title": title or "",
            "content": content or "",
            "key_points": kp,
            "raw": report_text or ""
        }
    return result

# ── 生成综合行情报告 ──────────────────────────────────────
def generate_report(trade_date: str, reviews: dict) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT index_name,price,pct_chg FROM daily_index WHERE trade_date=? ORDER BY pct_chg DESC", (trade_date,))
    indices = c.fetchall()

    c.execute("SELECT sector_name,pct_chg,lead_stock FROM daily_sector WHERE trade_date=? ORDER BY pct_chg DESC", (trade_date,))
    all_sectors = c.fetchall()

    # 主力净额正/负板块数量（等main_net查询完再关连接）
    c.execute("""
        SELECT COUNT(CASE WHEN main_net>0 THEN 1 END),
               COUNT(CASE WHEN main_net<0 THEN 1 END)
        FROM sector_moneyflow WHERE trade_date=? AND main_net IS NOT NULL
    """, (trade_date,))
    nc = c.fetchone()
    pos_cnt, neg_cnt = nc[0] or 0, nc[1] or 0

    # 主力净额 Top10
    c.execute("""
        SELECT sector_name, main_net, main_net_pct, price_chg
        FROM sector_moneyflow
        WHERE trade_date=? AND main_net IS NOT NULL
        ORDER BY main_net DESC LIMIT 10
    """, (trade_date,))
    top_net = c.fetchall()

    c.execute("""
        SELECT sector_name, main_net, main_net_pct, price_chg
        FROM sector_moneyflow
        WHERE trade_date=? AND main_net IS NOT NULL
        ORDER BY main_net ASC LIMIT 10
    """, (trade_date,))
    bot_net = c.fetchall()

    # 资金信号（净流入+涨幅适中）
    c.execute("""
        SELECT sector_name, main_net, price_chg
        FROM sector_moneyflow
        WHERE trade_date=? AND main_net>0 AND price_chg>0 AND price_chg<8
        ORDER BY main_net DESC LIMIT 8
    """, (trade_date,))
    opportunities = c.fetchall()

    # 关闭连接（后续不再查库）
    conn.close()

    def em(pct):
        try:
            v = float(pct)
            return "🔴" if v > 0 else ("🟢" if v < 0 else "⚪")
        except:
            return "⚪"

    def safe_pct(pct):
        try:
            return float(pct)
        except:
            return 0.0

    # ── 指数涨跌 ──
    sh_pct = 0.0
    for name, price, pct in indices:
        if "000001" in str(name) or "上证" in str(name):
            sh_pct = safe_pct(pct)
            break

    # ── 板块 ──
    pos = [(n,p,l) for n,p,l in all_sectors if safe_pct(p) > 0]
    neg = [(n,p,l) for n,p,l in all_sectors if safe_pct(p) < 0]
    neu = [(n,p,l) for n,p,l in all_sectors if safe_pct(p) == 0]
    top10 = pos[:10] if pos else all_sectors[:10]
    weak5 = sorted(all_sectors, key=lambda x: safe_pct(x[1]))[:5]

    lines = []
    lines.append("═" * 48)
    lines.append(f"  📊 {trade_date} 收盘综合报告")
    lines.append("═" * 48)

    # ── 午评摘要 ──
    wu_review = reviews.get("午评", {})
    if wu_review and wu_review.get("title"):
        lines.append("")
        lines.append("【午评回顾】")
        lines.append(f"  📰 {wu_review.get('title','')}")
        kp = wu_review.get("key_points", {})
        if isinstance(kp, dict):
            for line in kp.get("sector_hot", "").split("\n"):
                if line.strip(): lines.append(f"  {line.strip()}")
            for line in kp.get("market_summary", "").split("\n"):
                if line.strip(): lines.append(f"  {line.strip()}")
        elif isinstance(kp, str):
            for line in kp.split("\n"):
                if line.strip(): lines.append(f"  {line.strip()}")

    # ── 主要指数 ──
    lines.append("")
    lines.append("【主要指数】")
    for name, price, pct in indices:
        try:
            price_s = f"{float(price):,.2f}" if price else "—"
        except:
            price_s = str(price)
        lines.append(f"  {em(pct)} {name:<10} {price_s:<12} {safe_pct(pct):>+6.2f}%")

    # ── 板块 ──
    lines.append("")
    lines.append("【强势板块 Top10】")
    for i, (name, pct, lead) in enumerate(top10, 1):
        lines.append(f"  {em(pct)} {i:02d}. {name:<14} {safe_pct(pct):>+6.2f}%")

    lines.append("")
    lines.append("【弱势板块 Top5】")
    for i, (name, pct, lead) in enumerate(weak5, 1):
        lines.append(f"  {em(pct)} {i:02d}. {name:<14} {safe_pct(pct):>+6.2f}%")

    # ── 主力净额 Top10（已在上方提前查询） ──────────────────
    if top_net:
        lines.append("")
        lines.append(f"【主力净流入 Top10】（全市场{pos_cnt}↑/{neg_cnt}↓板块）")
        lines.append(f"  {'板块':<14} {'主力净额':>12} {'净占比':>7} {'涨跌幅':>8}")
        for name, net, net_pct, chg in top_net:
            pct_str = f"{net_pct:.2f}%" if net_pct else "—"
            lines.append(f"  {name:<14} {net:>+12,.0f}万 {pct_str:>7} {chg:>+7.2f}%")

    if bot_net:
        lines.append("")
        lines.append("【主力净流出 Top10】")
        lines.append(f"  {'板块':<14} {'主力净额':>12}")
        for name, net, _, _ in bot_net:
            lines.append(f"  {name:<14} {net:>+12,.0f}万")

    if opportunities:
        lines.append("")
        lines.append("【资金信号·机会识别】")
        for name, net, chg in opportunities:
            if net > 100000:
                sig = "🔥"
            elif net > 50000:
                sig = "✅"
            elif net > 20000:
                sig = "⚙️"
            else:
                sig = "➡️"
            lines.append(f"  {sig} {name}: 主力+{net:,.0f}万元 涨幅{chg:+.2f}%")

    # ── 收评摘要（含后市分析） ──
    shou_review = reviews.get("收评", {})
    if shou_review and shou_review.get("title"):
        lines.append("")
        lines.append("【收市点评】")
        lines.append(f"  📰 {shou_review.get('title','')}")
        kp = shou_review.get("key_points", {})
        if isinstance(kp, dict):
            if kp.get("market_summary"):
                for line in kp["market_summary"].split("\n"):
                    if line.strip(): lines.append(f"  {line.strip()}")
            if kp.get("sector_hot"):
                for line in kp["sector_hot"].split("\n"):
                    if line.strip(): lines.append(f"  {line.strip()}")
            if kp.get("opportunities"):
                lines.append("")
                lines.append("  💡 后续机会：")
                for line in kp["opportunities"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")
            if kp.get("risks"):
                lines.append("")
                lines.append("  ⚠️ 风险提示：")
                for line in kp["risks"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")
            if kp.get("outlook"):
                lines.append("")
                lines.append("  📋 后市研判：")
                for line in kp["outlook"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")
        elif isinstance(kp, str):
            for line in kp.split("\n"):
                if line.strip(): lines.append(f"  {line.strip()}")

    # ── 焦点复盘摘要 ─────────────────────────────────────────
    focus = reviews.get("焦点复盘", {})
    if focus and focus.get("title"):
        lines.append("")
        lines.append("【焦点复盘】")
        lines.append(f"  📰 {focus.get('title','')}")
        kp = focus.get("key_points", {})
        if isinstance(kp, dict):
            if kp.get("market_summary"):
                lines.append("")
                lines.append("  📊 市场概况：")
                for line in kp["market_summary"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")
            if kp.get("sector_hot"):
                lines.append("")
                lines.append("  🔥 热点解析：")
                for line in kp["sector_hot"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")
            if kp.get("opportunities"):
                lines.append("")
                lines.append("  💡 机会方向：")
                for line in kp["opportunities"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")
            if kp.get("risks"):
                lines.append("")
                lines.append("  ⚠️ 风险警示：")
                for line in kp["risks"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")
            if kp.get("outlook"):
                lines.append("")
                lines.append("  📋 后市展望：")
                for line in kp["outlook"].split("\n"):
                    if line.strip(): lines.append(f"    {line.strip()}")

    # ── 市场情绪 ────────────────────────────────────────────
    lines.append("")
    lines.append("─" * 48)
    if sh_pct > 1.5:
        mood, mood_emoji = "强势突破  做多情绪高涨", "🔥"
    elif sh_pct > 0.5:
        mood, mood_emoji = "小幅上涨  结构分化", "📈"
    elif sh_pct > -0.5:
        mood, mood_emoji = "窄幅震荡  多空僵持", "⚖"
    elif sh_pct > -1.5:
        mood, mood_emoji = "小幅回调  谨慎情绪", "📉"
    else:
        mood, mood_emoji = "明显下挫  注意风险", "⚠️"
    lines.append(f"  {mood_emoji} 市场情绪：{mood}")

    # ── 机会与风险 ──
    if pos and len(pos) > 0:
        top_s = pos[0]
        if safe_pct(top_s[1]) > 3:
            lines.append(f"  ✅ 机会：{top_s[0]} 强势领涨+{safe_pct(top_s[1]):.1f}%，板块效应较强")
    if neg and len(neg) > 0:
        bot_s = neg[-1]
        if safe_pct(bot_s[1]) < -2:
            lines.append(f"  ⚠️ 风险：{bot_s[0]} 领跌{safe_pct(bot_s[1]):.1f}%，注意回避")
    if len(neg) > 15:
        lines.append(f"  ⚠️ 风险：下跌板块{len(neg)}个，整体偏弱，控制仓位")

    # ── 涨跌家数估算 ──
    try:
        up_pct = len(pos) / max(len(all_sectors), 1) * 100
        lines.append(f"  📊 上涨板块占比：{up_pct:.0f}%（{len(pos)}/{len(all_sectors)}）")
    except:
        pass

    lines.append("")
    lines.append(f"═" * 48)

    return "\n".join(lines)

# ── 主程序 ─────────────────────────────────────────────────
def main():
    now = datetime.now(TZ_CST)
    trade_date = now.strftime("%Y-%m-%d")
    weekday = now.weekday()

    if weekday >= 5:
        print(f"[SKIP] 周末({['一','二','三','四','五','六','日'][weekday]})跳过")
        return

    print(f"[INFO] 开始采集 {trade_date} 综合报告...")

    # 0. 确保数据库初始化
    init_db()

    # 1. 读取午评/收评
    print("[1/4] 读取午评/收评...")
    reviews = get_reviews(trade_date)
    has_wu = "午评" in reviews and reviews["午评"].get("title")
    has_shou = "收评" in reviews and reviews["收评"].get("title")
    print(f"      午评:{'✅' if has_wu else '❌未入库'}  收评:{'✅' if has_shou else '❌未入库'}")

    # 2. 采集指数
    print("[2/4] 采集主要指数...")
    indices = fetch_major_indices(trade_date)
    if not indices:
        print("[WARN] 指数数据为空，可能已收盘或API异常")
        return

    # 3. 采集板块
    print("[3/4] 采集行业板块...")
    sectors = fetch_top_sectors(trade_date, 30)

    # 4. 入库
    print("[4/4] 入库...")
    init_db()
    save_to_db(indices, sectors)

    # 5. 生成报告（融合午评+收评）
    report = generate_report(trade_date, reviews)
    print()
    print(report)

    # 6. 保存报告
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO daily_market (trade_date, report_text) VALUES (?,?)",
              (trade_date, report))
    conn.commit()
    conn.close()

    return report

if __name__ == "__main__":
    main()
