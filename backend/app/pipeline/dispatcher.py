"""
dispatcher — 两阶段幂等投递（slim-v3 §3，唯一投递权威）。

状态机约束：
  - DUP 预检在扣配额/写 SENDING **之前**（runner 读 observed_label 后调 mark_dup，
    DUP 由 PENDING 直接置入，不经 CLAIMED/SENDING，不计配额——A5）
  - dispatch_one 只取 CLAIMED；先写 SENDING 再设备操作，回写 SENT/FAILED
  - 永不自动重拾 SENDING（崩溃恢复由 scan_sending() 推人工确认）
  - 任何发送必经 RateLimiter.check_and_consume_apply(rules.daily_limit)
  - 夜停读 RulesConfig（与 runner 子态判定同一真值源）
"""
from __future__ import annotations

import asyncio
from datetime import datetime, time as dtime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, ApplicationStatus, RunLog
from app.pipeline.rate_limiter import rate_limiter
from app.rules import RulesConfig

if TYPE_CHECKING:
    from app.pages.boss_wxapp import BossWxappDriver as BossDriver


def _parse_hhmm(s: str, default: dtime) -> dtime:
    try:
        h, m = s.split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        return default


def is_night_stop(rules: RulesConfig) -> bool:
    """夜停判定。读 rules.night_stop_*（与 runner 共用同一真值源）。"""
    start = _parse_hhmm(rules.night_stop_start, dtime(23, 0))
    end = _parse_hhmm(rules.night_stop_end, dtime(7, 0))
    now = datetime.now().time()
    if start <= end:
        return start <= now <= end
    # 跨午夜
    return now >= start or now <= end


def _log(session: Session, event: str, message: str,
         app_id: Optional[int] = None, level: str = "INFO") -> None:
    session.add(RunLog(event=event, message=message, application_id=app_id, level=level))


# ---------------------------------------------------------------------------
# 启动自检：扫描 SENDING 推人工确认（AC8/A10）
# ---------------------------------------------------------------------------


def scan_sending() -> list[int]:
    """
    启动时调用。返回仍处于 SENDING 状态的 Application id 列表。
    这些记录需人工在前端确认（已发/未发 → SENT/FAILED）。
    不自动改状态，避免二次发送。
    """
    with Session(engine) as session:
        stuck = session.exec(
            select(Application).where(Application.status == ApplicationStatus.SENDING)
        ).all()
        ids = [a.id for a in stuck]
        if ids:
            _log(
                session,
                "scan_sending",
                f"发现 {len(ids)} 条 SENDING 记录，需人工确认: {ids}",
            )
            session.commit()
    return ids


# ---------------------------------------------------------------------------
# DUP：设备层上报"继续沟通"，dispatcher 译为终态（决策权在此，不在设备层）
# ---------------------------------------------------------------------------


def mark_dup(application_id: int) -> None:
    """已投过（详情页"继续沟通"）→ PENDING 直接置 DUP。

    不调用 check_and_consume_apply、不写 SENDING（A5：DUP 不计配额）。
    """
    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None:
            return
        app.status = ApplicationStatus.DUP
        app.updated_at = datetime.now()
        session.add(app)
        _log(session, "dup", "已投过（继续沟通），跳过且不计配额", app.id)
        session.commit()


# ---------------------------------------------------------------------------
# 单次投递（runner 编排调用；调用时人已停在目标岗位详情页）
# ---------------------------------------------------------------------------


async def dispatch_one(
    application_id: int,
    driver: "BossDriver",
    rules: RulesConfig,
) -> str:
    """对单个 CLAIMED Application 执行两阶段投递。

    返回 "SENT" | "FAILED" | "SKIP"。
    前置：runner 已完成 DUP 预检（"继续沟通"不会进入本函数）且人在详情页。
    """
    # --- 夜停（双保险：runner 子态已挡，此处兜底）---
    if is_night_stop(rules):
        return "SKIP"

    # --- 配额检查（唯一入口）---
    allowed = await rate_limiter.check_and_consume_apply(daily_limit=rules.daily_limit)
    if not allowed:
        return "SKIP"

    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None or app.status != ApplicationStatus.CLAIMED:
            return "SKIP"

        # --- 阶段一：写 SENDING ---
        app.status = ApplicationStatus.SENDING
        app.updated_at = datetime.now()
        session.add(app)
        session.commit()

    # --- 阶段二：设备操作（阻塞 adb 调用放线程池，防塞事件循环）---
    ok, greeting, fail_reason = await asyncio.to_thread(driver.tap_chat_and_capture)

    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None:
            return "FAILED"
        if ok:
            app.status = ApplicationStatus.SENT
            app.sent_at = datetime.now()
            app.greeting = greeting          # 实发招呼语存证（A6）
            _log(session, "apply", "投递成功", app.id)
        else:
            app.status = ApplicationStatus.FAILED
            app.fail_reason = fail_reason or "投递验证失败"
            _log(session, "apply_fail", app.fail_reason, app.id, level="WARNING")
        app.updated_at = datetime.now()
        session.add(app)
        session.commit()
        return app.status.value
