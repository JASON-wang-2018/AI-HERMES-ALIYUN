#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书Webhook推送模块
参考 ZhuLinsen/daily_stock_analysis 的 feishu_sender.py 改造

功能：
- 飞书自定义机器人 Webhook 推送
- 签名认证（HMAC-SHA256）
- 关键词前缀
- 超长消息智能分片（按 ### 或 --- 分割）
- 卡片模式 + 文本模式双保险
"""

import hashlib
import hmac
import base64
import time
import json
import logging
import requests
from typing import Optional, List

logger = logging.getLogger(__name__)

# 飞书限制：单条消息最大 20KB（实际用 18KB 留余量）
FEISHU_MAX_BYTES = 18 * 1024


def _calc_sign(secret: str, timestamp: str) -> str:
    """计算签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    return base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")


def _chunk_by_size(content: str, max_bytes: int = FEISHU_MAX_BYTES) -> List[str]:
    """
    按字节数硬截断分割（保底）
    先尝试按 ### 章节分割，再按 --- 分段，最后按换行分割
    """
    if len(content.encode("utf-8")) <= max_bytes:
        return [content]

    # 策略1：按 ### 分割（保留分隔符）
    sections = content.split("\n### ")
    if len(sections) > 1:
        result = []
        buf = sections[0]
        for sec in sections[1:]:
            if len(buf.encode("utf-8")) + 4 + len(sec.encode("utf-8")) <= max_bytes:
                buf += "\n### " + sec
            else:
                if buf:
                    result.append(buf)
                buf = "### " + sec
        if buf:
            result.append(buf)
        if all(len(p.encode("utf-8")) <= max_bytes for p in result):
            return result

    # 策略2：按 --- 分割
    parts = content.split("\n---\n")
    if len(parts) > 1:
        result = []
        buf = ""
        for p in parts:
            chunk = (buf + "\n---\n" + p) if buf else p
            if len(chunk.encode("utf-8")) <= max_bytes:
                buf = chunk
            else:
                if buf:
                    result.append(buf)
                # 如果单段仍然超限，用\n\n截断
                if len(p.encode("utf-8")) > max_bytes:
                    lines = p.split("\n\n")
                    buf = ""
                    for line in lines:
                        test = (buf + "\n\n" + line) if buf else line
                        if len(test.encode("utf-8")) <= max_bytes:
                            buf = test
                        else:
                            if buf:
                                result.append(buf)
                            # 极长单行，按字符数硬截
                            raw = line.encode("utf-8")
                            buf = (buf + "\n\n" + line) if buf else line
                    if buf:
                        result.append(buf)
                    buf = ""
                else:
                    buf = p
        if buf:
            result.append(buf)
        if result and all(len(p.encode("utf-8")) <= max_bytes for p in result):
            return result

    # 策略3：按\n\n分割（段落模式）
    paras = content.split("\n\n")
    result = []
    buf = ""
    for p in paras:
        test = (buf + "\n\n" + p) if buf else p
        if len(test.encode("utf-8")) <= max_bytes:
            buf = test
        else:
            if buf:
                result.append(buf)
            buf = p
    if buf:
        result.append(buf)

    # 策略4：保底——按字节数硬截断（每4KB一切）
    if not result:
        raw = content.encode("utf-8")
        step = max_bytes
        for i in range(0, len(raw), step):
            chunk = raw[i:i+step].decode("utf-8", errors="ignore")
            result.append(chunk)

    # 过滤空段
    return [p for p in result if p.strip()]


def _build_card_payload(content: str, keyword: str = "") -> dict:
    """构建飞书交互卡片payload"""
    header_title = "📊 纳福A股分析报告"
    card_content = content
    if keyword and keyword not in content:
        card_content = f"**{keyword}**\n\n{content}"

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": "purple"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": card_content
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "由纳福AI自动生成 · "}
                    ]
                }
            ]
        }
    }


def _build_text_payload(content: str, keyword: str = "") -> dict:
    """构建飞书文本消息payload"""
    text = content
    if keyword and keyword not in content:
        text = f"**{keyword}**\n\n{content}"
    return {"msg_type": "text", "content": {"text": text}}


def send_to_feishu(
    content: str,
    webhook_url: str,
    secret: Optional[str] = None,
    keyword: Optional[str] = None,
    use_card: bool = True,
    max_bytes: int = FEISHU_MAX_BYTES,
) -> bool:
    """
    发送消息到飞书群

    :param content: 消息内容（Markdown格式）
    :param webhook_url: 飞书Webhook地址
    :param secret: 签名密钥（可选，有则启用签名认证）
    :param keyword: 关键词前缀（可选，消息必须包含该词才通过飞书校验）
    :param use_card: 是否使用交互卡片（默认True，卡片展示更美观）
    :param max_bytes: 单条最大字节数（默认18KB）
    :return: 发送是否成功
    """
    if not content or not content.strip():
        logger.warning("飞书推送内容为空，跳过")
        return True

    # 分割消息
    chunks = _chunk_by_size(content, max_bytes)
    logger.info(f"飞书消息分片：共{len(chunks)}片")

    success = True
    for i, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            # 片头标记（中间片需要承接上下文）
            if i > 1:
                chunk = f"（续第{i}页）\n{chunk}"
            if i < len(chunks):
                chunk = f"{chunk}\n（未完，待续第{i+1}页…）"

        # 签名
        timestamp = str(int(time.time()))
        headers = {"Content-Type": "application/json"}
        if secret:
            sign = _calc_sign(secret, timestamp)
            headers["X-Lark-Signature"] = sign
            headers["X-Lark-Timestamp"] = timestamp

        # 构建payload
        if use_card:
            payload = _build_card_payload(chunk, keyword or "")
        else:
            payload = _build_text_payload(chunk, keyword or "")

        try:
            resp = requests.post(
                webhook_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=10
            )
            result = resp.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                logger.info(f"飞书片{i}发送成功")
            else:
                # 卡片模式失败，尝试降级文本模式
                logger.warning(f"飞书片{i}卡片发送失败: {result}，尝试降级文本模式")
                payload_text = _build_text_payload(chunk, keyword or "")
                resp2 = requests.post(
                    webhook_url,
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(payload_text),
                    timeout=10
                )
                result2 = resp2.json()
                if result2.get("code") == 0 or result2.get("StatusCode") == 0:
                    logger.info(f"飞书片{i}文本模式发送成功")
                else:
                    logger.error(f"飞书片{i}文本模式也失败: {result2}")
                    success = False
        except Exception as e:
            logger.error(f"飞书片{i}发送异常: {e}")
            success = False

        # 片间间隔1秒防限流
        if i < len(chunks):
            time.sleep(1.0)

    return success


def send_report_to_jason(content: str) -> bool:
    """
    快捷方法：发送报告到Jason的飞书群
    使用环境变量 FEISHU_WEBHOOK_URL 和 FEISHU_WEBHOOK_SECRET
    """
    import os
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        logger.error("FEISHU_WEBHOOK_URL 环境变量未设置")
        return False

    secret = os.environ.get("FEISHU_WEBHOOK_SECRET", "")
    keyword = os.environ.get("FEISHU_WEBHOOK_KEYWORD", "纳福")

    return send_to_feishu(
        content=content,
        webhook_url=webhook_url,
        secret=secret or None,
        keyword=keyword,
        use_card=True,
    )


# ============================================================
# 测试
# ============================================================
if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    test_content = """
# 个股分析报告

## Step 1 · 定性定位
【阶段定位】：强势拉升后的三重超买高风险区

## Step 2 · 10维度技术验证
| 维度 | 状态 |
|------|------|
| 均线 | ✅ 多头 |
| RSI | 🔴 超买 |

## Step 3 · 综合评分：58/100

---

## 综合研判
中期趋势向上，但三重超买信号高度共振，节前效应叠加，回调是大概率事件。

---

### 操作建议
已有仓位者明日冲高减仓，节前最后一日收盘前轻仓，空仓者节后再战。

---

### 风控要点
- 硬止损：6.74元
- RSI预警：RSI6>85连续2日即减仓信号

---

### 基本面验证
- 全称：亚宝药业集团股份有限公司
- 主营：药品研发、生产、销售
- 行业(三级)：医药生物-中药Ⅱ-中药Ⅲ

---

### 估值水平
- PE=15.0，PB=1.68，市值=48亿
- 板块：中药Ⅱ

---
    """.strip()

    # 从环境变量读取webhook（未配置时跳过实际发送）
    url = os.environ.get("FEISHU_WEBHOOK_URL")
    if url:
        result = send_to_feishu(test_content, url, secret=os.environ.get("FEISHU_WEBHOOK_SECRET") or None)
        print(f"发送结果: {'成功' if result else '失败'}")
    else:
        # 模拟分割测试
        chunks = _chunk_by_size(test_content)
        print(f"分片测试（共{len(chunks)}片）:")
        for i, c in enumerate(chunks, 1):
            print(f"  片{i}: {len(c)}字 / {len(c.encode('utf-8'))}字节")
