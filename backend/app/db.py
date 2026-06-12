"""
数据库引擎与 session 工厂。
调用 init_db() 创建所有表（建 data/ 目录若不存在）。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

# 从 database_url 解析本地 sqlite 路径，确保目录存在
_db_url = settings.database_url
if _db_url.startswith("sqlite:///"):
    _path = _db_url[len("sqlite:///"):]
    _dir = os.path.dirname(_path)
    if _dir:
        os.makedirs(_dir, exist_ok=True)

engine = create_engine(
    _db_url,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite 跨线程
)


def init_db() -> None:
    """建表（idempotent）。应在 FastAPI lifespan 中调用。"""
    # 延迟导入确保所有 model 已注册到 SQLModel.metadata
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """同步 session 上下文管理器。"""
    with Session(engine) as session:
        yield session


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends 用法。"""
    with Session(engine) as session:
        yield session
