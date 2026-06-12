"""applications — 投递看板 + SENDING 待确认队列 + 人工确认归位（AC8）。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.db import get_db
from app.models import Application, ApplicationStatus, Job
from app.security.auth import require_auth

router = APIRouter(prefix="/applications", tags=["applications"])


def _app_dict(a: Application, job: Optional[Job] = None) -> dict:
    d = {
        "id": a.id,
        "job_id": a.job_id,
        "status": a.status.value,
        "greeting": a.greeting,
        "taken_over": a.taken_over,
        "fail_reason": a.fail_reason,
        "sent_at": a.sent_at.isoformat() if a.sent_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
    if job is not None:
        d["job"] = {
            "title": job.title,
            "company": job.company,
            "salary": job.salary,
            "salary_min_k": job.salary_min_k,
            "salary_max_k": job.salary_max_k,
            "area": job.area,
            "jd": job.jd,
            "score": job.score,
            "reasons": job.reasons,
            "degree": job.degree,
            "experience": job.experience,
            "company_scale": job.company_scale,
            "finance_stage": job.finance_stage,
            "hr_name": job.hr_name,
            "hr_active": job.hr_active,
        }
    return d


@router.get("", dependencies=[Depends(require_auth)])
async def list_applications(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    """投递历史记录（join Job 全字段，支撑核对看板 A6）。"""
    stmt = select(Application, Job).join(Job, Application.job_id == Job.id)  # type: ignore[arg-type]
    if status_filter:
        try:
            st = ApplicationStatus(status_filter.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status filter: {status_filter}",
            )
        stmt = stmt.where(Application.status == st)
    stmt = stmt.order_by(Application.id.desc())  # type: ignore[attr-defined]
    rows = db.exec(stmt.offset(skip).limit(limit)).all()
    return [_app_dict(a, j) for a, j in rows]


@router.delete("/clear", dependencies=[Depends(require_auth)])
async def clear_history(db: Session = Depends(get_db)) -> dict:
    """清空全部投递历史（application/job/message/run_log/quota），保留规则配置。

    必须注册在 /{app_id} 之前，否则 "clear" 会被当作 app_id 匹配。
    """
    from sqlmodel import delete

    from app.models import Job, Message, Quota, RunLog

    counts: dict[str, int] = {}
    for model in (Message, RunLog, Application, Job, Quota):
        res = db.exec(delete(model))
        counts[model.__tablename__] = res.rowcount or 0
    db.commit()
    return {"cleared": counts}


@router.get("/sending", dependencies=[Depends(require_auth)])
async def list_sending(db: Session = Depends(get_db)) -> list[dict]:
    """SENDING 待人工确认队列（AC8 崩溃恢复）。"""
    apps = db.exec(
        select(Application).where(Application.status == ApplicationStatus.SENDING)
    ).all()
    return [_app_dict(a) for a in apps]


@router.get("/{app_id}", dependencies=[Depends(require_auth)])
async def get_application(app_id: int, db: Session = Depends(get_db)) -> dict:
    a = db.get(Application, app_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return _app_dict(a)


@router.post("/{app_id}/confirm", dependencies=[Depends(require_auth)])
async def confirm_sending(
    app_id: int,
    body: dict,
    db: Session = Depends(get_db),
) -> dict:
    """人工确认 SENDING 记录归位（sent=True→SENT，sent=False→FAILED）。AC8。"""
    a = db.get(Application, app_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    if a.status != ApplicationStatus.SENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application is not in SENDING state (current: {a.status.value})",
        )
    sent = bool(body.get("sent", False))
    a.status = ApplicationStatus.SENT if sent else ApplicationStatus.FAILED
    a.fail_reason = "" if sent else str(body.get("reason", "manual_confirm_failed"))
    if sent:
        a.sent_at = datetime.now()
    a.updated_at = datetime.now()
    db.add(a)
    db.commit()
    db.refresh(a)
    return _app_dict(a)


@router.post("/{app_id}/takeover", dependencies=[Depends(require_auth)])
async def takeover(app_id: int, db: Session = Depends(get_db)) -> dict:
    """标记人工接管（inbox_watcher 发现 HR 回复后前端一键接管）。"""
    a = db.get(Application, app_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    a.taken_over = True
    a.updated_at = datetime.now()
    db.add(a)
    db.commit()
    db.refresh(a)

    return _app_dict(a)
