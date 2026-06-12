"""logs — 日志/成本 SSE 流 + REST 查询（鉴权 AC12/AC13）。"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.db import get_db
from app.models import RunLog
from app.security.auth import require_auth

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", dependencies=[Depends(require_auth)])
async def list_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    event: str = Query("", alias="event"),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(RunLog).order_by(RunLog.ts.desc())
    if event:
        stmt = stmt.where(RunLog.event == event)
    logs = db.exec(stmt.offset(skip).limit(limit)).all()
    return [_log_dict(log) for log in logs]


@router.get("/quota", dependencies=[Depends(require_auth)])
async def get_quota(db: Session = Depends(get_db)) -> dict:
    """今日投递配额快照。daily_apply_limit 取规则页 rules.daily_limit，
    与 runner /pipeline/status 同源，避免设备卡与投递面板显示不一致。"""
    from app.pipeline.rate_limiter import rate_limiter
    from app.rules import load_rules
    rules = load_rules(db)
    return await rate_limiter.get_quota(daily_limit=rules.daily_limit)


@router.get("/stream", dependencies=[Depends(require_auth)])
async def stream_logs() -> StreamingResponse:
    """SSE 日志流：客户端订阅后，新 RunLog 实时推送。"""
    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_generator() -> AsyncIterator[str]:
    """轮询 RunLog 表，推送新条目。生产环境可替换为消息队列。"""
    last_id = 0
    # seed last_id from DB
    from app.db import engine
    from sqlmodel import Session as S

    with S(engine) as session:
        latest = session.exec(
            select(RunLog).order_by(RunLog.id.desc()).limit(1)
        ).first()
        if latest:
            last_id = latest.id or 0

    while True:
        await asyncio.sleep(1.0)
        with S(engine) as session:
            new_logs = session.exec(
                select(RunLog)
                .where(RunLog.id > last_id)
                .order_by(RunLog.id)
                .limit(50)
            ).all()
        for log in new_logs:
            last_id = log.id
            data = json.dumps(_log_dict(log), ensure_ascii=False)
            yield f"data: {data}\n\n"


def _log_dict(entry: RunLog) -> dict:
    return {
        "id": entry.id,
        "ts": entry.ts.isoformat() if entry.ts else None,
        "level": entry.level,
        "event": entry.event,
        "message": entry.message,
        "application_id": entry.application_id,
        "job_id": entry.job_id,
    }
