#!/usr/bin/env python3
"""
午评/收评 数据存储工具
被 12:45 午评cronjob 和 17:15 收评cronjob 调用
也供 18:00 行情报告读取
"""
import sqlite3, os
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.expanduser("~/stock_knowledge/database/daily_market.db")
TZ_CST = timezone(timedelta(hours=8))

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
    conn.commit()
    conn.close()

def save_review(trade_date: str, review_type: str, title: str = None,
                content: str = None, key_points: str = None, report_text: str = None):
    """
    保存午评或收评到数据库
    review_type: '午评' 或 '收评'
    title: 文章标题
    content: 正文摘要
    key_points: 精炼要点（早盘热点/午后动态/机会/风险等）
    report_text: 原始报告文本（用于兼容）
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO daily_review
        (trade_date, review_type, title, content, key_points, report_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (trade_date, review_type, title, content, key_points, report_text))
    conn.commit()
    conn.close()
    print(f"[OK] {trade_date} {review_type} 已入库")

def get_review(trade_date: str, review_type: str = None):
    """读取指定日期的午评/收评"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if review_type:
        c.execute("SELECT * FROM daily_review WHERE trade_date=? AND review_type=?",
                  (trade_date, review_type))
    else:
        c.execute("SELECT * FROM daily_review WHERE trade_date=? ORDER BY review_type",
                  (trade_date,))
    rows = c.fetchall()
    conn.close()
    cols = ["id","trade_date","review_type","title","content","key_points","report_text","created_at"]
    return [dict(zip(cols, r)) for r in rows]

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: daily_review_storage.py <trade_date> <午评|收评> [title] [content] [key_points]")
        sys.exit(1)
    trade_date = sys.argv[1]
    review_type = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else None
    content = sys.argv[4] if len(sys.argv) > 4 else None
    key_points = sys.argv[5] if len(sys.argv) > 5 else None
    save_review(trade_date, review_type, title, content, key_points)
