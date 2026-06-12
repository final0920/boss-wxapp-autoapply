"""messages — HR 对话消息（鉴权 AC12）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.db import get_db
from app.models import Application, ApplicationStatus, Message
from app.security.auth import require_auth

router = APIRouter(prefix="/messages", tags=["messages"])


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "application_id": m.application_id,
        "role": m.role.value,
        "text": m.text,
        "ts": m.ts.isoformat() if m.ts else None,
    }


@router.get("", dependencies=[Depends(require_auth)])
async def list_messages(
    application_id: int = Query(...),
    db: Session = Depends(get_db),
) -> list[dict]:
    msgs = db.exec(
        select(Message)
        .where(Message.application_id == application_id)
        .order_by(Message.ts)
    ).all()
    return [_msg_dict(m) for m in msgs]


@router.get("/inbox", dependencies=[Depends(require_auth)])
async def inbox(db: Session = Depends(get_db)) -> list[dict]:
    """收件箱：已投递（SENT）且未接管的会话 + 最新 HR 消息，供前端一键接管。

    注意：此路由必须注册在 /{msg_id} 之前，否则 'inbox' 会被当作 msg_id。
    """
    apps = db.exec(
        select(Application)
        .where(Application.status == ApplicationStatus.SENT)
        .where(Application.taken_over.is_(False))
    ).all()
    result: list[dict] = []
    for a in apps:
        last = db.exec(
            select(Message)
            .where(Message.application_id == a.id)
            .order_by(Message.ts.desc())
            .limit(1)
        ).first()
        result.append({
            "application_id": a.id,
            "job_id": a.job_id,
            "taken_over": a.taken_over,
            "last_message": _msg_dict(last) if last else None,
        })
    return result


@router.post("/{msg_id}/read", dependencies=[Depends(require_auth)])
async def mark_read(msg_id: int) -> dict:
    """标记消息已读（stub）。TODO 真机阶段：Message.read 字段持久化。"""
    return {"id": msg_id, "read": True}


@router.get("/{msg_id}", dependencies=[Depends(require_auth)])
async def get_message(msg_id: int, db: Session = Depends(get_db)) -> dict:
    m = db.get(Message, msg_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return _msg_dict(m)
