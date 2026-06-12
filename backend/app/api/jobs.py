"""jobs — 岗位列表/详情/打分/黑名单（鉴权 AC12）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.db import get_db
from app.models import Job
from app.security.auth import require_auth

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", dependencies=[Depends(require_auth)])
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    jobs = db.exec(select(Job).offset(skip).limit(limit)).all()
    return [_job_dict(j) for j in jobs]


@router.get("/{job_id}", dependencies=[Depends(require_auth)])
async def get_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_dict(job)


@router.post("/fetch", dependencies=[Depends(require_auth)])
async def trigger_fetch() -> dict:
    """触发岗位抓取（stub）。

    TODO(M3): runner 融合循环落地后，由 runner 编排 BossDriver 采集 + collector 入库。
    当前返回占位，便于前端按钮联调。
    """
    return {"triggered": True, "note": "stub — M3 接 runner/collector"}


@router.post("/{job_id}/blacklist", dependencies=[Depends(require_auth)])
async def set_blacklist(job_id: int, body: dict) -> dict:
    """加入/移出黑名单（stub）。

    TODO 真机阶段：持久化（需 Job.blacklisted 字段 + 迁移），筛选时跳过。
    """
    return {"id": job_id, "blacklisted": bool(body.get("blacklisted", True))}


@router.post("/{job_id}/pin", dependencies=[Depends(require_auth)])
async def set_pin(job_id: int, body: dict) -> dict:
    """置顶/取消置顶（stub）。

    TODO 真机阶段：持久化（需 Job.pinned 字段 + 迁移）。
    """
    return {"id": job_id, "pinned": bool(body.get("pinned", True))}


def _job_dict(j: Job) -> dict:
    # reasons 持久化为 JSON 字符串（screener 输出 list[str]），这里解析回数组供前端渲染
    try:
        reasons = json.loads(j.reasons) if j.reasons else []
        if not isinstance(reasons, list):
            reasons = [str(reasons)]
    except (ValueError, TypeError):
        reasons = [j.reasons] if j.reasons else []
    return {
        "id": j.id,
        "title": j.title,
        "company": j.company,
        "salary": j.salary,
        "area": j.area,
        "jd": j.jd,
        "score": j.score,
        "reasons": reasons,
        # 黑名单/置顶暂无持久化（真机阶段加 Job 字段 + 迁移），默认 false
        "blacklisted": False,
        "pinned": False,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }
