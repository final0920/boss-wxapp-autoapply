"""
RateLimiter — 投递配额 + VLM 调用预算唯一真相源。

持久化到 Quota 表，重启后配额不丢失。
"""
from __future__ import annotations

import asyncio
from datetime import date

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Quota

# 模块级异步锁，防止并发双写 Quota
_lock = asyncio.Lock()


def _today() -> str:
    return date.today().isoformat()


def _get_or_create_quota(session: Session, day: str) -> Quota:
    stmt = select(Quota).where(Quota.date == day)
    q = session.exec(stmt).first()
    if q is None:
        q = Quota(date=day)
        session.add(q)
        session.commit()
        session.refresh(q)
    return q


# ---------------------------------------------------------------------------
# 同步核心（被异步包装调用）
# ---------------------------------------------------------------------------


def _sync_check_apply(daily_limit: int) -> bool:
    """检查并消耗一次投递配额。返回 False 表示今日已达上限。"""
    day = _today()
    with Session(engine) as session:
        q = _get_or_create_quota(session, day)
        if q.apply_count >= daily_limit:
            return False
        q.apply_count += 1
        session.add(q)
        session.commit()
        return True


def _sync_get_quota(daily_limit: int) -> dict:
    day = _today()
    with Session(engine) as session:
        q = _get_or_create_quota(session, day)
        return {
            "date": day,
            "apply_count": q.apply_count,
            "daily_apply_limit": daily_limit,
        }


def _sync_check_consume_vlm(daily_budget: int) -> bool:
    """检查并消耗一次 VLM 调用配额。返回 False 表示今日已达上限（熔断）。"""
    day = _today()
    with Session(engine) as session:
        q = _get_or_create_quota(session, day)
        if q.vlm_count >= daily_budget:
            return False
        q.vlm_count += 1
        q.updated_at = __import__("datetime").datetime.now()
        session.add(q)
        session.commit()
        return True


def _sync_get_vlm_quota(daily_budget: int) -> dict:
    day = _today()
    with Session(engine) as session:
        q = _get_or_create_quota(session, day)
        count = q.vlm_count
    return {
        "date": day,
        "today_vlm_calls": count,
        "vlm_daily_budget": daily_budget,
        "vlm_circuit_open": count >= daily_budget,
    }


# ---------------------------------------------------------------------------
# 公开异步接口
# ---------------------------------------------------------------------------


class RateLimiter:
    """
    全局单例限速器。

    用法：
        from app.pipeline.rate_limiter import rate_limiter
        ok = await rate_limiter.check_and_consume_apply(daily_limit=rules.daily_limit)
        ok = await rate_limiter.check_and_consume_vlm()
    """

    async def check_and_consume_apply(
        self,
        daily_limit: int = settings.daily_apply_limit,
    ) -> bool:
        """消耗一次投递配额。超限返回 False。

        Args:
            daily_limit: 当日最大投递数，从 rules.daily_limit 传入；
                         未传时回退 settings.daily_apply_limit 保持向后兼容。
        """
        async with _lock:
            return _sync_check_apply(daily_limit)

    async def get_quota(
        self,
        daily_limit: int = settings.daily_apply_limit,
    ) -> dict:
        """返回今日配额快照（用于前端成本监控/日志）。"""
        async with _lock:
            return _sync_get_quota(daily_limit)

    async def check_and_consume_vlm(
        self,
        daily_budget: int = settings.vlm_daily_budget,
    ) -> bool:
        """消耗一次 VLM 调用配额。超限返回 False（熔断）。"""
        async with _lock:
            return _sync_check_consume_vlm(daily_budget)

    async def get_vlm_quota(
        self,
        daily_budget: int = settings.vlm_daily_budget,
    ) -> dict:
        """返回今日 VLM 配额快照（today_vlm_calls/vlm_daily_budget/vlm_circuit_open）。"""
        async with _lock:
            return _sync_get_vlm_quota(daily_budget)

    async def reset_quota_for_test(self) -> None:
        """仅供测试使用：重置今日配额（含 VLM）。"""
        day = _today()
        async with _lock:
            with Session(engine) as session:
                stmt = select(Quota).where(Quota.date == day)
                q = session.exec(stmt).first()
                if q:
                    q.apply_count = 0
                    q.vlm_count = 0
                    session.add(q)
                    session.commit()


# 全局单例
rate_limiter = RateLimiter()
