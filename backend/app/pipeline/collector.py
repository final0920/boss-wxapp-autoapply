"""
collector — 抓取岗位并去重，建 Application(PENDING)。

去重键：jd_hash = SHA-256(company + title + jd[:200])
重复 jd_hash 忽略（不建新 Application）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, ApplicationStatus, Job
from app.pipeline.screener import parse_salary


@dataclass
class RawJob:
    """从 Boss 直聘页面抓取到的原始岗位数据。"""
    title: str
    company: str
    salary: str = ""
    area: str = ""
    jd: str = ""
    # 列表页标签字段（fl_require_info 来源）；M3 详情页抓到后会覆盖 Job 表
    degree: str = ""
    experience: str = ""
    # 列表卡片扩展字段（D0 固化：tv_scale/tv_stage/tv_employer/tv_active_status）
    company_scale: str = ""
    finance_stage: str = ""
    hr_name: str = ""
    hr_title: str = ""    # HR 职务（如"猎头顾问"/"人力资源经理"），用于猎头/代招过滤
    hr_active: str = ""


def _make_jd_hash(company: str, title: str, jd: str) -> str:
    raw = f"{company}\x00{title}\x00{jd[:200]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def collect_jobs(
    raw_jobs: list[RawJob],
    account_id: str = "default",
    device_id: str = "default",
) -> list[int]:
    """
    将原始岗位列表写入 DB，对每个新岗位建 Application(PENDING)。
    返回新建 Application 的 id 列表。

    幂等：相同 jd_hash 跳过，不重复建投递记录。
    入库时解析 salary 写入 salary_min_k / salary_max_k。
    """
    new_app_ids: list[int] = []

    with Session(engine) as session:
        for raw in raw_jobs:
            jd_hash = _make_jd_hash(raw.company, raw.title, raw.jd)

            # 去重：检查 Job 是否已存在
            existing_job = session.exec(
                select(Job).where(Job.jd_hash == jd_hash)
            ).first()

            if existing_job is not None:
                # 已有 Job，检查是否已有 Application
                existing_app = session.exec(
                    select(Application).where(
                        Application.job_id == existing_job.id,
                        Application.account_id == account_id,
                        Application.device_id == device_id,
                    )
                ).first()
                if existing_app is not None:
                    continue  # 完全重复，跳过
                job = existing_job
            else:
                sal_min, sal_max = parse_salary(raw.salary)
                job = Job(
                    title=raw.title,
                    company=raw.company,
                    salary=raw.salary,
                    area=raw.area,
                    jd=raw.jd,
                    jd_hash=jd_hash,
                    salary_min_k=sal_min if sal_min > 0 else None,
                    salary_max_k=sal_max if sal_max > 0 else None,
                    degree=raw.degree,
                    experience=raw.experience,
                    company_scale=raw.company_scale,
                    finance_stage=raw.finance_stage,
                    hr_name=raw.hr_name,
                    hr_active=raw.hr_active,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                session.add(job)
                session.flush()  # 获取 job.id

            # 建 Application(PENDING)
            app = Application(
                job_id=job.id,
                account_id=account_id,
                device_id=device_id,
                status=ApplicationStatus.PENDING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(app)
            session.flush()
            new_app_ids.append(app.id)

        session.commit()

    return new_app_ids
