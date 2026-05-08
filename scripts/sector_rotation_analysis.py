#!/usr/bin/env python3
"""
板块轮动分析器
功能：
  1. 读取历史nightly_collect JSON，提取板块资金流Top5
  2. 读取历史热点日报JSON，提取概念涨幅排行
  3. 识别轮动路径（行业→子行业→概念层层演绎）
  4. 计算各板块"持续天数"和"强度"
  5. 预判明日可能轮动方向
"""
import json, os, sys
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = "/home/admin/stock_knowledge"
DB_DIR = os.path.join(BASE_DIR, "database")
REPORT_DIR = os.path.join(BASE_DIR, "reports")

# 导入选股模块
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
try:
    from screen_rotation_stocks import run_screening
    HAS_SCREENER = True
except Exception as e:
    HAS_SCREENER = False
    _screen_err = str(e)


def load_nightly_collects():
    """加载所有历史nightly_collect JSON"""
    files = sorted([f for f in os.listdir(DB_DIR)
                    if f.startswith("nightly_collect_20260")])
    result = {}
    for f in files:
        date = f.replace("nightly_collect_", "").replace(".json", "")
        with open(os.path.join(DB_DIR, f)) as fh:
            d = json.load(fh)
        result[date] = {
            "industry_top20": d.get("industry_money_top20", []),
            "concept_top20": d.get("concept_money_top20", []),
            "industry_hot": d.get("industry_hot_top10", []),
            "concept_hot": d.get("concept_hot_top10", []),
        }
    return result


def load_hot_reports():
    """加载所有历史热点日报JSON"""
    files = sorted([f for f in os.listdir(REPORT_DIR)
                    if f.startswith("热点日报_") and f.endswith(".json")])
    result = {}
    for f in files:
        date = f.replace("热点日报_", "").replace(".json", "")
        with open(os.path.join(REPORT_DIR, f)) as fh:
            d = json.load(fh)
        result[date] = {
            "sector_fund_flow": d.get("sector_fund_flow", {}),  # name -> {change_pct, main_net}
            "concept_performance": d.get("concept_performance", {}),
            "sentiment": d.get("sentiment", {}),
            "zt_count": d.get("zt_count", 0),
            "index_data": d.get("index_data", {}),
        }
    return result


def get_sector_ranking(days_dict: dict, top_n: int = 10) -> list:
    """
    从多日数据中统计板块出现频次和平均排名
    days_dict: {date: {industry_top20: [...]}}
    返回: [(板块名, 出现次数, 平均排名得分, 最近日期), ...]
    """
    scores = defaultdict(lambda: {"count": 0, "rank_sum": 0, "dates": []})
    for date, data in sorted(days_dict.items()):
        top20 = data.get("industry_top20", []) or data.get("industry_hot", [])
        if not top20:
            continue
        for i, item in enumerate(top20[:top_n]):
            if isinstance(item, dict):
                name = item.get("name", "")
            else:
                name = str(item)
            if name:
                scores[name]["count"] += 1
                scores[name]["rank_sum"] += (top_n - i)
                scores[name]["dates"].append(date)
    # 计算综合得分：频次 × 平均排名分
    result = []
    for name, s in scores.items():
        avg_rank = s["rank_sum"] / s["count"] if s["count"] > 0 else 0
        final_score = s["count"] * avg_rank
        result.append((name, s["count"], avg_rank, final_score, s["dates"][-1]))
    result.sort(key=lambda x: -x[3])
    return result


def trace_rotation_path(nc_data: dict, lookback_days: int = 7) -> list:
    """
    追踪最近N天的板块轮动路径
    返回: [(date, rank1, rank2, rank3, ...)]
    """
    dates = sorted(nc_data.keys())[-lookback_days:]
    path = []
    for date in dates:
        data = nc_data.get(date, {})
        top5 = data.get("industry_top20", []) or data.get("industry_hot", [])
        if not top5:
            continue
        ranks = [(item.get("name") if isinstance(item, dict) else str(item))
                 for item in top5[:5]]
        path.append((date, *ranks))
    return path


def calc_sector_momentum(nc_data: dict) -> dict:
    """
    计算各板块动量（用于预判持续性）
    近3天持续上榜=强动量，近1天新上榜=新热点
    """
    dates = sorted(nc_data.keys())[-3:]
    scores = defaultdict(lambda: {"days": [], "total_rank_score": 0})

    for date in dates:
        data = nc_data.get(date, {})
        top10 = data.get("industry_top20", []) or data.get("industry_hot", [])
        if not top10:
            continue
        for i, item in enumerate(top10[:10]):
            name = item.get("name") if isinstance(item, dict) else str(item)
            if name:
                scores[name]["days"].append(date)
                scores[name]["total_rank_score"] += (10 - i)

    momentum = {}
    for name, s in scores.items():
        days_count = len(s["days"])
        if days_count >= 3:
            label = "🔥 持续强势"
        elif days_count == 2:
            label = "★ 动量增强"
        elif days_count == 1:
            label = "→ 新晋热点"
        else:
            label = "- 减弱"
        momentum[name] = {
            "label": label,
            "days": days_count,
            "rank_score": s["total_rank_score"],
            "last_seen": s["days"][-1] if s["days"] else ""
        }
    return momentum


def predict_rotation(momentum: dict, recent_winner: str) -> list:
    """
    基于轮动规律预判明日方向
    规律1: 资金从高位板块向低位板块切换
    规律2: 概念炒作周期: 启动(1-2天)→扩散(3-5天)→高潮(5-7天)→退潮
    规律3: 轮动顺序: 有色→科技→消费→金融→地产→基建→...
    """
    predictions = []

    # 找高位（连续3天强势）板块
    high_momentum = {n: d for n, d in momentum.items() if d["days"] >= 3}
    # 找新晋热点
    new_hot = {n: d for n, d in momentum.items() if d["days"] == 1}

    # 预判1: 持续强势板块延续
    for name, d in sorted(high_momentum.items(), key=lambda x: -x[1]["rank_score"])[:3]:
        predictions.append({
            "type": "🔥 延续强势",
            "sector": name,
            "confidence": "高",
            "reason": f"已持续{d['days']}天强势，主力资金持续流入"
        })

    # 预判2: 新晋热点扩散
    for name, d in sorted(new_hot.items(), key=lambda x: -x[1]["rank_score"])[:2]:
        predictions.append({
            "type": "→ 热点扩散",
            "sector": name,
            "confidence": "中",
            "reason": "新晋热点，明日可能向同产业链扩散"
        })

    # 预判3: 轮动至相邻板块
    related = {
        "通信设备": ["光通信模块", "光纤", "F5G", "CPO"],
        "半导体": ["集成电路制造", "芯片设计", "半导体设备", "光刻胶"],
        "国防军工": ["军工电子", "航空装备", "卫星导航", "无人机"],
        "通信": ["通信设备", "光通信模块", "5G概念", "F5G"],
    }
    if recent_winner in related:
        for adjacent in related[recent_winner][:2]:
            if adjacent not in high_momentum:
                predictions.append({
                    "type": "⟳ 产业链轮动",
                    "sector": adjacent,
                    "confidence": "中",
                    "reason": f"受{recent_winner}带动，资金可能向相邻板块扩散"
                })

    return predictions


def generate_rotation_report() -> str:
    nc_data = load_nightly_collects()
    hot_data = load_hot_reports()

    if not nc_data:
        return "数据不足，无法生成轮动分析"

    # 1. 轮动路径
    path = trace_rotation_path(nc_data, lookback_days=7)

    # 2. 板块动量
    momentum = calc_sector_momentum(nc_data)

    # 3. 预判
    recent_dates = sorted(nc_data.keys())[-1:]
    recent_top = nc_data.get(recent_dates[0], {}).get("industry_top20", []) or []
    recent_winner = recent_top[0].get("name") if (recent_top and isinstance(recent_top[0], dict)) else str(recent_top[0] if recent_top else "")
    predictions = predict_rotation(momentum, recent_winner)

    # 4. 生成报告
    lines = []
    lines.append("═" * 56)
    lines.append("  📈 板块轮动分析报告")
    lines.append(f"  数据范围: 最近7个交易日")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("═" * 56)

    lines.append("\n【一、近7日板块轮动路径】")
    lines.append("  日期       第1主线        第2主线       第3主线")
    lines.append("  " + "-" * 50)
    for entry in path:
        date = entry[0]
        ranks = list(entry[1:])
        row = f"  {date}  "
        for i, r in enumerate(ranks[:3]):
            tag = "🔴" if i == 0 else "🟡" if i == 1 else "🟢"
            row += f"  {tag}{r}"
        lines.append(row)

    lines.append("\n【二、板块动量排行榜】")
    lines.append("  动量标签        板块名称            持续天数  综合得分")
    lines.append("  " + "-" * 52)
    sorted_momentum = sorted(momentum.items(), key=lambda x: (-x[1]["days"], -x[1]["rank_score"]))
    for name, d in sorted_momentum[:12]:
        label = d["label"]
        spaces = "  " if len(label) <= 6 else " "
        lines.append(f"  {label}{spaces}{name:<16}  {d['days']}天       {d['rank_score']:.0f}")

    lines.append("\n【三、板块生命周期判断】")
    for name, d in sorted_momentum[:8]:
        if d["days"] >= 5:
            status = "⚠️ 高潮后期（警惕退潮）"
        elif d["days"] >= 3:
            status = "🔥 加速期（继续持有）"
        elif d["days"] == 2:
            status = "★ 扩散期（可跟进）"
        elif d["days"] == 1:
            status = "→ 启动期（观察）"
        else:
            status = "- 退潮期（回避）"
        lines.append(f"  {name}: {status}")

    lines.append("\n【四、明日轮动预判】")
    if predictions:
        for i, p in enumerate(predictions[:6], 1):
            lines.append(f"  {i}. 【{p['type']}】{p['sector']}  (置信度:{p['confidence']})")
            lines.append(f"     → {p['reason']}")
    else:
        lines.append("  数据不足，无法预判")

    lines.append("\n【五、轮动规律总结】")
    all_sectors = []
    for data in nc_data.values():
        top = data.get("industry_top20", []) or data.get("industry_hot", [])
        for item in top[:5]:
            name = item.get("name") if isinstance(item, dict) else str(item)
            if name:
                all_sectors.append(name)
    from collections import Counter
    top_sectors = Counter(all_sectors).most_common(5)
    lines.append("  近7日主力资金最高频上榜板块:")
    for name, cnt in top_sectors:
        days_count = sum(1 for d in nc_data.values()
                        if any(item.get("name") == name if isinstance(item, dict) else str(item) == name
                               for item in (d.get("industry_top20", []) or d.get("industry_hot", []))[:5]))
        pct = days_count / max(len(nc_data), 1) * 100
        lines.append(f"    • {name}: 出现{days_count}天({pct:.0f}%)")

    lines.append("\n" + "═" * 56)
    return "\n".join(lines)


def get_screening_results():
    """读取今日选股结果JSON"""
    today = datetime.now().strftime("%Y%m%d")
    path = os.path.join(REPORT_DIR, f"轮动选股_{today}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def generate_screening_section():
    """生成【六、潜力个股】章节"""
    results = get_screening_results()
    if not results:
        return ""

    lines = []
    lines.append("\n【六、潜力个股】")
    lines.append("  市值来源：东方财富f116字段（已校准：特发信息=181亿✓）")
    lines.append("  筛选条件：市值≤300亿 | 股价≤30元 | 概念匹配轮动热点")
    lines.append(f"  候选总数：{len(results)}只")
    lines.append("")
    lines.append("  🔥 强烈关注（评分≥85）：")
    strong = [r for r in results if r["score"] >= 85]
    if not strong:
        lines.append("  （无）")
    else:
        for r in strong[:10]:
            mcap_str = f"{r['mcap']:.0f}亿"
            lines.append(
                f"    {r['symbol']} {r['name']:<8} 价:{r['price']:>5.2f}元 "
                f"涨:{r['pct_chg']:>5.2f}%  市值:{mcap_str:>6} "
                f"RSI:{r['rsi']:.0f} 距低:{r['dist_low']:>4.0f}%  "
                f"[{r['hot_tag']}/{r['tag']}]"
            )

    lines.append("")
    lines.append("  ★ 值得关注（评分60-84）：")
    mid = [r for r in results if 60 <= r["score"] < 85]
    if not mid:
        lines.append("  （无）")
    else:
        for r in mid[:8]:
            mcap_str = f"{r['mcap']:.0f}亿"
            lines.append(
                f"    {r['symbol']} {r['name']:<8} 价:{r['price']:>5.2f}元 "
                f"涨:{r['pct_chg']:>5.2f}%  市值:{mcap_str:>6} "
                f"RSI:{r['rsi']:.0f} 距低:{r['dist_low']:>4.0f}%  "
                f"[{r['hot_tag']}/{r['tag']}]"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    # 1. 生成轮动分析
    report = generate_rotation_report()

    # 2. 运行选股筛选
    print("🔍 正在运行潜力个股筛选...")
    if HAS_SCREENER:
        try:
            run_screening()
            print("✅ 选股完成")
        except Exception as e:
            print(f"⚠️ 选股失败: {e}")
    else:
        print(f"⚠️ 选股模块不可用: {_screen_err}")

    # 3. 读取选股结果，追加到报告
    screening_text = generate_screening_section()
    if screening_text:
        report += screening_text

    print(report)

    # 保存
    today = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(REPORT_DIR, f"板块轮动分析_{today}.txt")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"\n已保存: {out_path}")
