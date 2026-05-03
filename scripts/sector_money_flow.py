#!/usr/bin/env python3
"""
东财板块资金流采集 → 入库SQLite
主力净额：f62字段（单位元，/10000转为万元）
用法: python3 sector_money_flow.py
"""
import sqlite3, subprocess, re, os, json
from datetime import datetime, timezone, timedelta

TZ_CST = timezone(timedelta(hours=8))
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "daily_market.db")

def curl(url: str) -> str:
    cmd = [
        "curl", "-s", "-L", url,
        "-H", "Referer: https://data.eastmoney.com/",
        "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return r.stdout

def fetch_sector_moneyflow(pagesize=100) -> list:
    """
    抓取东财板块资金流（主力净额）
    fs=m:90+t:2 = 行业板块（全部）
    fid=f62 按主力净额排序
    f62=主力净额(元), f3=涨跌幅, f14=板块名称, f12=板块代码
    需要分两次取：正序（净流入最大）+ 倒序（净流出最大）
    """
    seen = set()
    result = []
    # 第一次：主力净额从大到小（取最多，正流入）
    url = (
        f"https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={pagesize}&po=1&np=1&fltt=2&invt=2&fid=f62"
        f"&fs=m:90+t:2"
        f"&fields=f2,f3,f5,f6,f7,f12,f14,f62,f184"
        f"&_={int(datetime.now(TZ_CST).timestamp())}"
    )
    raw = curl(url)
    try:
        d = json.loads(raw)
        items = d["data"]["diff"]
        for item in items:
            if item["f12"] not in seen:
                seen.add(item["f12"])
                result.append(item)
    except Exception as e:
        print(f"[WARN] 正序解析失败: {e}")

    # 第二次：主力净额从小到大（净流出最大）
    url2 = (
        f"https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={pagesize}&po=0&np=1&fltt=2&invt=2&fid=f62"
        f"&fs=m:90+t:2"
        f"&fields=f2,f3,f5,f6,f7,f12,f14,f62,f184"
        f"&_={int(datetime.now(TZ_CST).timestamp())+1}"
    )
    raw2 = curl(url2)
    try:
        d2 = json.loads(raw2)
        items2 = d2["data"]["diff"]
        for item in items2:
            if item["f12"] not in seen:
                seen.add(item["f12"])
                result.append(item)
    except Exception as e:
        print(f"[WARN] 倒序解析失败: {e}")

    print(f"[INFO] 共获取 {len(result)} 个板块（去重后）")
    return result

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 扩展 daily_sector 表，追加主力净额字段
    c.execute("""
        CREATE TABLE IF NOT EXISTS sector_moneyflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            sector_code TEXT NOT NULL,
            sector_name TEXT NOT NULL,
            main_net REAL DEFAULT 0,      -- 主力净额(万元)
            main_net_pct REAL DEFAULT 0,  -- 主力净占比%
            price_chg REAL DEFAULT 0,     -- 涨跌幅%
            volume_ratio REAL DEFAULT 0,  -- 量比
            turnover REAL DEFAULT 0,       -- 换手率%
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, sector_code)
        )
    """)
    # 兼容旧库：如果 sector_moneyflow 表不存在但 daily_sector 有，就加字段
    try:
        c.execute("ALTER TABLE daily_sector ADD COLUMN main_net REAL DEFAULT NULL")
    except:
        pass
    conn.commit()
    conn.close()

def save_moneyflow(trade_date: str, data: list):
    """
    data: list of dict {
        f12: sector_code,
        f14: sector_name,
        f62: main_net (元),
        f184: main_net_pct (可选),
        f3: price_chg,
        f5: volume_ratio,
        f6: turnover
    }
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0
    for item in data:
        code = str(item.get("f12", ""))
        name = item.get("f14", "")
        main_net_yuan = item.get("f62", 0) or 0
        main_net_wan = round(main_net_yuan / 10000, 2)
        main_net_pct = round(item.get("f184", 0) or 0, 4)
        price_chg = round(item.get("f3", 0) or 0, 2)
        volume_ratio = round(item.get("f5", 0) or 0, 2)
        turnover = round(item.get("f6", 0) or 0, 2)

        c.execute("""
            INSERT OR REPLACE INTO sector_moneyflow
            (trade_date, sector_code, sector_name, main_net, main_net_pct,
             price_chg, volume_ratio, turnover)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (trade_date, code, name, main_net_wan, main_net_pct,
              price_chg, volume_ratio, turnover))
        count += 1
    conn.commit()
    conn.close()
    return count

def get_top_sectors(trade_date: str, limit=20, sort="net") -> list:
    """读取主力净额前N板块"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    order = "main_net DESC" if sort == "net" else "ABS(main_net) DESC"
    c.execute(f"""
        SELECT sector_name, main_net, main_net_pct, price_chg, volume_ratio, turnover
        FROM sector_moneyflow
        WHERE trade_date=? AND main_net IS NOT NULL
        ORDER BY {order}
        LIMIT ?
    """, (trade_date, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_sector_net_summary(trade_date: str) -> dict:
    """汇总：净流入/净流出板块数量和金额"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT
            COUNT(CASE WHEN main_net > 0 THEN 1 END) as pos_cnt,
            COUNT(CASE WHEN main_net < 0 THEN 1 END) as neg_cnt,
            SUM(CASE WHEN main_net > 0 THEN main_net ELSE 0 END) as pos_sum,
            SUM(CASE WHEN main_net < 0 THEN main_net ELSE 0 END) as neg_sum
        FROM sector_moneyflow
        WHERE trade_date=? AND main_net IS NOT NULL
    """, (trade_date,))
    row = c.fetchone()
    conn.close()
    return {
        "pos_cnt": row[0] or 0,
        "neg_cnt": row[1] or 0,
        "pos_sum": row[2] or 0,
        "neg_sum": row[3] or 0,
    }

def print_report(trade_date: str):
    summary = get_sector_net_summary(trade_date)
    top_in = get_top_sectors(trade_date, 15, "net")
    top_out = get_top_sectors(trade_date, 15, "net_desc")
    # 取绝对值最大的（净流出最多的）
    top_out_neg = sorted(
        [(r[0], r[1]) for r in top_out if r[1] < 0],
        key=lambda x: x[1]
    )[:10]

    print(f"\n{'='*52}")
    print(f"  📊 板块资金流 {trade_date}")
    print(f"{'='*52}")
    print(f"\n【资金概况】")
    print(f"  净流入板块: {summary['pos_cnt']}个  合计 +{summary['pos_sum']:,.0f}万元")
    print(f"  净流出板块: {summary['neg_cnt']}个  合计 {summary['neg_sum']:,.0f}万元")

    print(f"\n【主力净流入前15】 ▲")
    print(f"  {'板块':<14} {'主力净额':>12} {'净占比':>7} {'涨跌幅':>8}")
    for name, net, net_pct, chg, vol, turn in top_in:
        pct_str = f"{net_pct:.2f}%" if net_pct else "—"
        print(f"  {name:<14} {net:>+12,.0f}万 {pct_str:>7} {chg:>+7.2f}%")

    print(f"\n【主力净流出前10】 ▼")
    print(f"  {'板块':<14} {'主力净额':>12}")
    for name, net in top_out_neg:
        print(f"  {name:<14} {net:>+12,.0f}万")

    print(f"\n{'='*52}")

    # 机会识别逻辑
    print(f"\n【资金信号·机会识别】")
    # 条件：主力净流入大(>5亿) + 涨幅适中(不追高)
    opportunities = [(n, net, chg) for n, net, npct, chg, vol, turn in top_in
                     if net > 50000 and chg > 0 and chg < 8]
    if opportunities:
        for n, net, chg in opportunities[:5]:
            level = "🔥强信号" if net > 100000 else "✅有机会"
            print(f"  {level} {n}: 主力+{net:,.0f}万元 涨幅{chg:+.2f}%")
    else:
        top_in_limit = [(n, net, chg) for n, net, npct, chg, vol, turn in top_in if net > 10000 and chg > 0][:5]
        for n, net, chg in top_in_limit:
            print(f"  ⚙️ 资金关注 {n}: 主力+{net:,.0f}万元 涨幅{chg:+.2f}%")

def main():
    now = datetime.now(TZ_CST)
    trade_date = now.strftime("%Y-%m-%d")
    weekday = now.weekday()
    if weekday >= 5:
        print(f"[SKIP] 周末跳过")
        return

    print(f"[INFO] 采集板块资金流 {trade_date} ...")
    data = fetch_sector_moneyflow(pagesize=100)
    if not data:
        print("[ERROR] 无数据")
        return

    count = save_moneyflow(trade_date, data)
    print(f"[OK] 入库 {count} 条板块资金流")

    # 输出报告
    print_report(trade_date)

if __name__ == "__main__":
    main()
