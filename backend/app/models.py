"""
SQLModel 数据模型。
所有表共享同一 SQLite 数据库（见 db.py）。

Application 状态机：PENDING -> CLAIMED -> SENDING -> SENT | FAILED
                    PENDING -> DUP（设备级"继续沟通"预检，不经 CLAIMED/SENDING）
  - dispatcher 只取 CLAIMED
  - SENDING 仅由启动自检转人工确认，永不自动重拾
  - taken_over=True 表示人工接管（inbox_watcher 发现 HR 回复后置）
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ApplicationStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    DUP = "DUP"


class MessageRole(str, enum.Enum):
    USER = "user"
    HR = "hr"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Job — 岗位
# ---------------------------------------------------------------------------


class Job(SQLModel, table=True):
    __tablename__ = "job"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    company: str = Field(index=True)
    salary: str = ""
    area: str = ""
    jd: str = ""
    # SHA-256(company+title+jd[:200]) 去重键
    jd_hash: str = Field(index=True, unique=True)
    score: Optional[float] = None
    reasons: str = ""          # JSON list[str]，screener 输出
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    # 详情页补全字段（detail_fetched_at 有值代表已抓过详情页）
    salary_min_k: Optional[float] = None
    salary_max_k: Optional[float] = None
    degree: str = ""
    experience: str = ""
    company_scale: str = ""
    finance_stage: str = ""
    hr_active: str = ""
    hr_name: str = ""
    detail_fetched_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Application — 投递记录（状态机）
# ---------------------------------------------------------------------------


class Application(SQLModel, table=True):
    __tablename__ = "application"

    id: Optional[int] = Field(default=None, primary_key=True)

    # --- 关联 ---
    job_id: int = Field(foreign_key="job.id", index=True)

    # --- 多账号/多设备扩展（schema 已预留，当前单账号） ---
    account_id: str = Field(default="default", index=True)
    device_id: str = Field(default="default", index=True)

    # --- 状态机 ---
    status: ApplicationStatus = Field(
        default=ApplicationStatus.PENDING, index=True
    )

    # --- 投递内容 ---
    greeting: str = ""          # 实发招呼语（投递成功后从聊天页抓回）

    # --- 时间戳 ---
    sent_at: Optional[datetime] = None
    last_poll_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # --- 接管标志（inbox_watcher 置 True） ---
    taken_over: bool = False

    # --- 失败原因 ---
    fail_reason: str = ""


# ---------------------------------------------------------------------------
# Message — HR 对话消息
# ---------------------------------------------------------------------------


class Message(SQLModel, table=True):
    __tablename__ = "message"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    role: MessageRole = Field(default=MessageRole.HR)
    text: str
    ts: datetime = Field(default_factory=datetime.now, index=True)


# ---------------------------------------------------------------------------
# Config — 运行时可调配置（前端设置页写入，覆盖 .env 默认）
# ---------------------------------------------------------------------------


class Config(SQLModel, table=True):
    __tablename__ = "config"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str = ""
    updated_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# RunLog — 运行日志（含 VLM 计数/后端切换/暂停原因，不记 key）
# ---------------------------------------------------------------------------


class RunLog(SQLModel, table=True):
    __tablename__ = "run_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=datetime.now, index=True)
    level: str = "INFO"         # INFO | WARNING | ERROR
    event: str = ""             # 事件类型，如 "apply" | "paused"
    message: str = ""
    application_id: Optional[int] = None
    job_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Quota — 每日配额追踪（RateLimiter 持久化来源）
# ---------------------------------------------------------------------------


class Quota(SQLModel, table=True):
    __tablename__ = "quota"

    id: Optional[int] = Field(default=None, primary_key=True)
    # 格式 YYYY-MM-DD
    date: str = Field(index=True, unique=True)
    apply_count: int = 0
    updated_at: datetime = Field(default_factory=datetime.now)
