#!/usr/bin/env python3
"""
光通信概念潜力个股筛选器 v5（整合版）
核心策略：
  1. 光通信核心股票池（~60只，主营明确，去除无关股）
  2. push2delay ulist API → f116字段获取总市值（/1e8=亿元），精确≤300亿过滤
  3. baostock K线数据 → 计算RSI/均线/量价/上市时间
  4. Tushare daily → 今日收盘价/涨跌幅
  5. 轮动报告热点 → 概念匹配加分
  6. 整合进 sector_rotation_analysis.py 的18:30报告中

市值字段：f116/1e8 = 亿元（已验证：浦发银行f116=3027亿≈实际2800亿）
"""
import json, os, sys, time, re, subprocess
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = "/home/admin/stock_knowledge"
REPORT_DIR = os.path.join(BASE_DIR, "reports")
MAX_MCAP = 300   # 亿元
MAX_PRICE = 30   # 元

# ══════════════════════════════════════════════════════════
# 光通信核心股票池（主营明确相关，人工审核）
# (exchange, symbol, name, tag, main_business)
# ══════════════════════════════════════════════════════════
OPTICAL_STOCKS = [
    # ── 光模块/光器件 ──
    ("SH", "603083", "剑桥科技", "光模块",    "高速光模块"),
    ("SZ", "300502", "新易盛",   "光模块",    "高速光模块封装"),
    ("SZ", "002281", "光迅科技", "光模块",    "光电子器件/模块"),
    ("SZ", "300308", "中际旭创", "光模块",    "光模块龙头"),
    ("SZ", "300394", "天孚通信", "光无源器件","高端光器件/陶瓷插芯"),
    ("SZ", "300570", "太辰光",   "光纤连接器","陶瓷插芯/光纤连接器"),
    ("SZ", "002902", "铭普光磁", "光磁元器件","光磁元器件/光模块"),
    ("SH", "688498", "源杰科技", "光芯片",    "半导体激光器芯片"),
    ("SH", "688313", "仕佳光子", "光芯片",    "PLC光分路器芯片"),
    # ── 光纤光缆 ──
    ("SH", "600487", "亨通光电", "光纤光缆",  "光纤光缆龙头"),
    ("SH", "600522", "中天科技", "光纤光缆",  "光纤光缆/海缆"),
    ("SH", "600498", "烽火通信", "光纤光缆",  "光通信系统设备"),
    ("SH", "600345", "长江通信", "光纤光缆",  "光通信系统/参股"),
    ("SH", "600105", "永鼎股份", "光纤光缆",  "光纤光缆/光模块"),
    ("SZ", "000070", "特发信息", "光纤光缆",  "光纤光缆/军工通信"),
    ("SZ", "000586", "汇源通信", "光纤光缆",  "光纤光缆"),
    ("SZ", "002491", "通鼎互联", "光纤光缆",  "光纤光缆/网络安全"),
    # ── 通信设备（光通信相关） ──
    ("SH", "603803", "瑞斯康达", "光通信设备","光网络终端/接入网"),
    ("SH", "600776", "东方通信", "通信设备",  "专网通信/基站"),
    ("SH", "600775", "南京熊猫", "通信设备",  "军工通信/电子装备"),
    ("SH", "600562", "国睿科技", "雷达/通信", "雷达及地面雷达"),
    ("SH", "600990", "四创电子", "雷达/通信", "雷达电子装备"),
    ("SZ", "000547", "航天发展", "军工通信",  "军用通信/电磁科技"),
    ("SZ", "002115", "龙宇股份", "IDC/光通信","IDC/大宗商品"),
    ("SH", "600131", "国网信通", "电力通信",  "电力信息通信"),
    ("SZ", "002313", "日海智能", "AIoT通信",  "AIoT/通信模组/光通信"),
    ("SH", "603220", "中贝通信", "通信服务",  "5G建设/光网络"),
    # ── 光通信辅材/材料 ──
    ("SH", "603186", "华正新材", "覆铜板/材料","覆铜板/光模块材料"),
    ("SZ", "002381", "双象股份", "光学材料",  "PMMA光学材料"),
    # ── 5G/通信设备 ──
    ("SH", "600050", "中国联通", "运营商",    "电信运营商"),
    ("SH", "601728", "中国电信", "运营商",    "电信运营商/云业务"),
    # ── 射频/天线（光通信基站相关） ──
    ("SZ", "300134", "大富科技", "射频器件",  "基站射频器件/滤波器"),
    # ── 半导体/集成电路（光通信产业链） ──
    ("SZ", "002185", "华天科技", "封装测试",  "集成电路封装"),
    ("SZ", "300623", "捷捷微电", "功率半导体","晶闸管/MOSFET"),
    ("SZ", "002484", "江海股份", "电容/铝电解","铝电解电容/薄膜电容"),
    ("SH", "688256", "寒武纪",   "AI芯片",    "云端AI芯片"),
]

# 去重
seen = set()
OPTICAL_STOCKS_DEDUPED = []
for ex, sym, name, tag, biz in OPTICAL_STOCKS:
    if sym not in seen:
        seen.add(sym)
        OPTICAL_STOCKS_DEDUPED.append((ex, sym, name, tag, biz))
OPTICAL_STOCKS = OPTICAL_STOCKS_DEDUPED


# ══════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════
def fv(v):
    """安全转float"""
    try:
        return float(v)
    except:
        return 0.0


def get_mcap_em_batch(stocks):
    """
    通过东方财富个股详情API批量获取总市值（36只，逐只查）
    f116/1e8 = 亿元（已校准：浦发银行=3027亿≈实际2800亿）
    stocks: [(exchange, symbol, name), ...]
    """
    if not stocks:
        return {}
    results = {}
    for i, (ex, sym, name) in enumerate(stocks):
        secid = f"{'1' if ex == 'SH' else '0'}.{sym}"
        url = (
            f"https://push2delay.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}"
            f"&fields=f12,f14,f2,f3,f43,f116,f47,f48"
            f"&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2"
        )
        r = subprocess.run(
            ["curl", "-s", "--max-time", "6", url],
            capture_output=True, text=True
        )
        try:
            data = json.loads(r.stdout)
            fields = data.get("data", {})
            price_raw = fv(fields.get("f43", 0))  # f43 = 今日收盘价/实时价(元)
            f116 = fv(fields.get("f116", 0))
            results[sym] = {
                "price": price_raw,      # f43 = 元（已验证：特发信息f43=20.11元）
                "mcap": f116 / 1e8,     # f116(元) / 1e8 = 亿元（已验证：特发信息=181亿）
            }
        except Exception as e:
            results[sym] = {"price": 0, "mcap": 0}
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(stocks)}] ...", end="", flush=True)
        time.sleep(0.5)
    return results


# ══════════════════════════════════════════════════════════
# Step 1: 读取轮动热点板块
# ══════════════════════════════════════════════════════════
def get_hot_sectors():
    today = datetime.now().strftime("%Y%m%d")
    path = Path(REPORT_DIR) / f"板块轮动分析_{today}.txt"
    if not path.exists():
        yd = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        path = Path(REPORT_DIR) / f"板块轮动分析_{yd}.txt"
    if not path.exists():
        return ["通信设备", "光通信模块", "通信", "光纤", "CPO", "F5G"]

    with open(path) as f:
        content = f.read()
    sectors = []
    for tag in ["→ 新晋热点", "⟳ 产业链轮动", "🔥 延续强势"]:
        for line in content.split("\n"):
            if tag in line:
                m = re.search(r"【[^】]+】(\S+)", line)
                if m:
                    sectors.append(m.group(1).strip())
    return list(dict.fromkeys(sectors))


# ══════════════════════════════════════════════════════════
# Step 2: Tushare今日行情
# ══════════════════════════════════════════════════════════
def get_tushare_prices():
    import tushare as ts
    pro = ts.pro_api("d46da9759ecdd402e8f8947feb7fc09c416496a7c7d5b79b47132997")
    today_str = datetime.now().strftime("%Y%m%d")
    for attempt in range(3):
        try:
            df = pro.daily(trade_date=today_str)
            print(f"  Tushare daily: {len(df)}只")
            return df.set_index("ts_code")
        except Exception as e:
            if "频率" in str(e):
                time.sleep(20)
            else:
                raise


# ══════════════════════════════════════════════════════════
# Step 3: 北向资金
# ══════════════════════════════════════════════════════════
def get_north_hold():
    import tushare as ts
    pro = ts.pro_api("d46da9759ecdd402e8f8947feb7fc09c416496a7c7d5b79b47132997")
    try:
        today = datetime.now().strftime("%Y%m%d")
        df = pro.hk_hold(trade_date=today)
        if df is None or df.empty:
            yd = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            df = pro.hk_hold(trade_date=yd)
        if df is not None and not df.empty:
            print(f"  北向持仓: {len(df)}只")
            return set(df["ts_code"].str[:6].tolist())
    except:
        pass
    return set()


# ══════════════════════════════════════════════════════════
# Step 4: baostock K线 + 上市时间
# ══════════════════════════════════════════════════════════
def get_kline_and_listdate(bs_code):
    import baostock as bs
    bs.login()
    # K线
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume",
        start_date=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
        end_date=datetime.now().strftime("%Y-%m-%d"),
        frequency="d"
    )
    kline = []
    while rs.error_code == "0" and rs.next():
        kline.append(rs.get_row_data())
    # 上市日期
    rs2 = bs.query_stock_basic(code=bs_code)
    list_date = None
    while rs2.error_code == "0" and rs2.next():
        row = rs2.get_row_data()
        if len(row) >= 3:
            list_date = row[2]
    bs.logout()
    return kline, list_date


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, min(period + 1, len(prices))):
        d = prices[-i] - prices[-i-1]
        gains.append(d if d > 0 else 0)
        losses.append(abs(d) if d < 0 else 0)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    return 100 - (100 / (1 + avg_gain / avg_loss))


# ══════════════════════════════════════════════════════════
# Step 5: 技术分析 + 综合评分
# ══════════════════════════════════════════════════════════
def analyze_stock(exchange, sym, name, tag, biz,
                  em_data, prices_df, north_hold, hot_sectors):
    """分析单只股票，返回评分结果或None"""
    ts_code = f"{sym}.{'SZ' if exchange == 'SZ' else 'SH'}"

    # 东方财富数据
    if sym not in em_data:
        return None
    em = em_data[sym]
    price = em["price"]
    mcap = em["mcap"]

    # 市值过滤
    if price <= 0 or price > MAX_PRICE:
        return None
    if mcap > MAX_MCAP:
        return None

    # Tushare涨跌幅
    pct = 0.0
    if ts_code in prices_df.index:
        pct = prices_df.loc[ts_code, "pct_chg"]

    # 热点匹配
    hot_match = False
    for s in hot_sectors:
        if any(kw in s for kw in ["通信", "光", "CPO", "F5G", "电子"]):
            if any(kw in name for kw in ["光", "通信", "光纤", "模块", "天孚", "剑桥", "中际", "新易", "特发", "汇源", "通鼎", "亨通", "烽火", "永鼎", "大富", "华天", "捷捷", "仕佳", "源杰", "光迅"]):
                hot_match = True
                break
        if "半导" in s and any(kw in tag for kw in ["半导", "封装", "芯片", "光芯片"]):
            hot_match = True
            break
    hot_tag = "🔥主线" if hot_match else "→相关"

    # K线 + 上市时间
    bs_code = f"{'sz' if exchange == 'SZ' else 'sh'}.{sym}"
    kline, list_date = get_kline_and_listdate(bs_code)
    if not kline or len(kline) < 20:
        return None

    closes = [float(k[4]) for k in kline if k[4]]
    vols = [float(k[5]) for k in kline[-25:] if k[5]]
    if not closes:
        return None
    current = closes[-1]

    # 上市年限（>1年为老股）
    is_old = False
    if list_date:
        try:
            list_dt = datetime.strptime(list_date, "%Y-%m-%d")
            list_years = (datetime.now() - list_dt).days / 365.25
            is_old = list_years > 1.0
        except:
            pass

    # RSI
    rsi = calc_rsi(closes)

    # 均线
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    ma多头 = ma5 > ma10 > ma20

    # 距低位
    low_20 = min(closes[-20:])
    dist_low = (current - low_20) / low_20 * 100

    # 近5日涨幅
    chg_5d = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0

    # 量能
    vol_ratio = (sum(vols[-5:]) / 5) / (sum(vols[-20:-5]) / max(len(vols[-20:-5]), 1)) if len(vols) >= 20 else 1

    # ── 评分 ──
    score = 50
    tags = []

    if 30 <= rsi <= 60:
        score += 20; tags.append(f"RSI={rsi:.0f}(低位)")
    elif 60 < rsi <= 68:
        score += 10; tags.append(f"RSI={rsi:.0f}(偏低价)")
    elif rsi > 75:
        score -= 15; tags.append(f"RSI={rsi:.0f}(高位⚠️)")
    else:
        tags.append(f"RSI={rsi:.0f}")

    if ma多头:
        score += 20; tags.append("均线多头")

    if dist_low < 15:
        score += 15; tags.append(f"低位启动{dist_low:.0f}%")
    elif dist_low > 50:
        score -= 10; tags.append(f"已涨{dist_low:.0f}%")

    if 0 <= chg_5d <= 8:
        score += 5; tags.append(f"近5日+{chg_5d:.1f}%")
    elif chg_5d > 20:
        score -= 5; tags.append(f"近5日急涨{chg_5d:.1f}%!")

    if vol_ratio > 1.5:
        score += 5; tags.append(f"量能{vol_ratio:.1f}x")
    elif vol_ratio < 0.6:
        score -= 5; tags.append("量萎")

    if is_old:
        pass  # 老股正常，不扣分
    else:
        score -= 5; tags.append("次新股<1年")

    if sym in north_hold:
        score += 5; tags.append("北向")

    if hot_match:
        score += 5; tags.append("热点匹配")

    score = max(0, min(100, score))

    return {
        "code": ts_code,
        "symbol": sym,
        "name": name,
        "price": price,
        "pct_chg": pct,
        "mcap": mcap,
        "tag": tag,
        "biz": biz,
        "hot_tag": hot_tag,
        "score": score,
        "rsi": rsi,
        "ma多头": ma多头,
        "dist_low": dist_low,
        "chg_5d": chg_5d,
        "vol_ratio": vol_ratio,
        "is_old": is_old,
        "tags": "; ".join(tags),
    }


# ══════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════
def run_screening():
    print("=" * 62)
    print("  🔍 光通信概念潜力个股筛选（v5 整合版）")
    print(f"  条件：市值≤{MAX_MCAP}亿 | 股价≤{MAX_PRICE}元 | 概念匹配轮动热点")
    print("=" * 62)

    hot = get_hot_sectors()
    print(f"\n📌 轮动热点: {hot}")

    # 构建股票列表
    stocks_list = [(ex, sym, name) for ex, sym, name, tag, biz in OPTICAL_STOCKS]
    print(f"\n📊 获取市值数据（东方财富个股详情API，{len(stocks_list)}只）...")
    em_data = get_mcap_em_batch(stocks_list)
    print(f"  市值数据获取: {len(em_data)}只")

    print("\n📊 获取今日行情（Tushare）...")
    prices_df = get_tushare_prices()
    north_hold = get_north_hold()

    print("\n🔬 开始技术分析...")
    results = []
    total = len(OPTICAL_STOCKS)
    for i, (ex, sym, name, tag, biz) in enumerate(OPTICAL_STOCKS, 1):
        print(f"\n[{i}/{total}] {sym} {name}({tag}) ...", end="", flush=True)
        r = analyze_stock(ex, sym, name, tag, biz, em_data, prices_df, north_hold, hot)
        if r is None:
            print(" ⏭️ 跳过")
            continue
        results.append(r)
        sym_ = "🔥" if r["score"] >= 70 else "★" if r["score"] >= 55 else "→"
        mcap_tag = f"{r['mcap']:.0f}亿" if r["mcap"] < 100 else f"{r['mcap']:.0f}亿"
        print(f"  {sym_}评分={r['score']:3.0f} | {r['tags']}")

    # 排序
    results.sort(key=lambda x: -x["score"])

    # 输出排行榜
    print("\n" + "=" * 62)
    print("  🏆 光通信概念潜力个股排行榜")
    print("=" * 62)
    print(f"  🔥≥70分=强烈关注  ★55-69分=值得关注  →50-54=观察")
    print()
    print(f"  {'Rk':<3}{'代码':<9}{'名称':<8}{'股价':>6}{'涨幅':>6}{'市值':>7}{'评分':>5}{'RSI':>5}{'距低位':>6} 标签/备注")
    print("  " + "-" * 75)
    for rank, r in enumerate(results[:20], 1):
        tag = "🔥" if r["score"] >= 70 else "★" if r["score"] >= 55 else "→"
        mcap_str = f"{r['mcap']:.0f}亿" if r["mcap"] < 200 else f"{r['mcap']:.0f}亿"
        print(f"  {tag}{rank:<3}{r['symbol']:<9}{r['name']:<8}"
              f"{r['price']:>5.2f}  {r['pct_chg']:>5.2f}%"
              f"  {mcap_str:>7}  {r['score']:3.0f}   {r['rsi']:4.0f}  {r['dist_low']:5.0f}%"
              f"  [{r['hot_tag']}/{r['tag']}]")

    # 保存
    today_str = datetime.now().strftime("%Y%m%d")
    out_json = Path(REPORT_DIR) / f"轮动选股_{today_str}.json"
    with open(out_json, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已保存: {out_json}")

    # 输出文字版供cron使用
    out_txt = Path(REPORT_DIR) / f"轮动选股_{today_str}.txt"
    lines = [
        "═" * 62,
        f"  光通信概念潜力个股筛选（v5）",
        f"  轮动热点: " + " | ".join(hot),
        f"  条件: 市值≤300亿 | 股价≤30元 | 概念匹配",
        f"  市值来源: 东方财富f116字段（已校准）",
        f"  生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "═" * 62, "",
        f"  {'Rk':<3}{'代码':<9}{'名称':<8}{'股价':>6}{'涨幅':>6}{'市值':>7}{'评分':>5}{'RSI':>5}{'距低位':>6} 标签/备注",
        "  " + "-" * 75,
    ]
    for rank, r in enumerate(results[:20], 1):
        tag = "🔥" if r["score"] >= 70 else "★" if r["score"] >= 55 else "→"
        mcap_str = f"{r['mcap']:.0f}亿" if r["mcap"] < 200 else f"{r['mcap']:.0f}亿"
        lines.append(
            f"  {tag}{rank:<3}{r['symbol']:<9}{r['name']:<8}"
            f"{r['price']:>5.2f}  {r['pct_chg']:>5.2f}%"
            f"  {mcap_str:>7}  {r['score']:3.0f}   {r['rsi']:4.0f}  {r['dist_low']:5.0f}%"
            f"  [{r['hot_tag']}/{r['tag']}]"
        )
    lines.append("═" * 62)
    with open(out_txt, "w") as f:
        f.write("\n".join(lines))
    print(f"✅ 已保存: {out_txt}")

    return results


if __name__ == "__main__":
    run_screening()
