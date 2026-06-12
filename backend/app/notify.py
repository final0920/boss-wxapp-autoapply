"""通知模块 — HR 回复通知（Web SSE + 可选 Telegram）。

AC18 PII 分层：
  - RunLog.message（SSE/日志可见）：仅存 event + application_id，不含 company/snippet/account_id。
  - Telegram 通知：含可选摘要，仅在明确配置后发送。
  - 完整 PII（company/message_text）由已鉴权的 /messages 端点查询。
不记录 Authorization/token（AC14）。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_hr_reply(
    application_id: int,
    job_title: str,
    company: str,
    message_text: str,
    device_id: str = "default",
    account_id: str = "default",
    truncate_len: int = 100,
) -> None:
    """触发 HR 回复通知（同步，可在线程中调用）。

    message_text 截断后发送，不含完整 PII（AC18）。
    """
    # 截断消息体，减少 PII 外发
    snippet = message_text[:truncate_len] + ("..." if len(message_text) > truncate_len else "")

    payload = {
        "event": "hr_reply",
        "application_id": application_id,
        "job_title": job_title,
        "company": company,
        "message_snippet": snippet,
        "device_id": device_id,
        "account_id": account_id,
    }

    logger.info("HR reply notification: app_id=%d company=%s", application_id, company)

    # Web SSE 广播：仅存 application_id，完整 PII 不写日志（L1/AC18）
    _emit_sse_event(application_id)

    # 可选 Telegram 通知（需配置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID）
    _try_telegram(payload)


def _emit_sse_event(application_id: int) -> None:
    """写入 RunLog 作为 SSE 事件载体（/logs/stream 轮询 RunLog）。

    L1: 只存 event + application_id，不含 company/snippet/account_id（AC18）。
    完整 PII 由已鉴权的 /messages 端点查询。
    """
    try:
        import json
        from datetime import datetime

        from app.db import engine
        from app.models import RunLog
        from sqlmodel import Session

        minimal = {"event": "hr_reply", "application_id": application_id}
        with Session(engine) as session:
            log = RunLog(
                ts=datetime.now(),
                level="INFO",
                event="hr_reply",
                message=json.dumps(minimal),
                application_id=application_id,
            )
            session.add(log)
            session.commit()
    except Exception as exc:
        logger.debug("_emit_sse_event error: %s", exc)


def _try_telegram(payload: dict) -> None:
    """可选 Telegram 通知；缺配置时静默跳过。"""
    try:
        import os

        import httpx

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            return

        text = (
            f"[Boss 直聘] HR 回复\n"
            f"岗位：{payload['job_title']} @ {payload['company']}\n"
            f"摘要：{payload['message_snippet']}"
        )
        # 同步发送（notify 在线程中调用）
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5.0,
        )
    except Exception as exc:
        logger.debug("Telegram notify error: %s", exc)
