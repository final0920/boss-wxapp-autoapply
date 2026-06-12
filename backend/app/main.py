"""
FastAPI + python-socketio ASGI 组合入口

lifespan:
  - 初始化 DB（建表）
  - 启动自检 scan_sending（AC8）
  - 注册 scrcpy Socket.IO 命名空间
  - shutdown：停止调度器

BIND_HOST 由 uvicorn 启动命令读取（见 __main__ 块）。
无真机也应能 import 启动（设备相关惰性导入）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Socket.IO server（默认命名空间鉴权；/scrcpy 命名空间在 lifespan 注册）
# ---------------------------------------------------------------------------

sio = socketio.AsyncServer(
    async_mode="asgi",
    # transport 层放行（含经 vite 代理的跨端口 Origin）；真正的 Origin/token 校验
    # 在 connect 事件的 sio_auth_ok 中完成。空列表会在握手层直接 403，sio_auth_ok
    # 根本跑不到。localhost-bind + sio_auth_ok(Origin+token) 已是纵深防御。
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None) -> bool:
    """默认命名空间 connect：鉴权 (AC12)。"""
    from app.security.auth import sio_auth_ok

    if not sio_auth_ok(environ):
        logger.warning("Socket.IO 连接已拒绝 sid=%s", sid)
        return False
    logger.debug("Socket.IO 已连接 sid=%s", sid)
    return True


@sio.event
async def disconnect(sid: str) -> None:
    logger.debug("Socket.IO 已断开 sid=%s", sid)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 启动初始化（建表/崩溃自检/scrcpy 命名空间注册）已移至模块级
    # _startup_init()（见 asgi_app 构造前）。原因：socketio.ASGIApp 包装下
    # FastAPI 的 lifespan scope 不被转发执行——曾导致 /scrcpy 命名空间从未注册、
    # 投屏空白。lifespan 仅保留 shutdown 钩子（若运行环境恰好转发则生效）。
    logger.info("boss-autoapply lifespan enter bind_host=%s", settings.bind_host)
    yield

    # --- shutdown ---
    # runner 真停（A11：无悬挂 Task）
    from app.pipeline.runner import runner  # noqa: PLC0415
    if runner.is_active():
        logger.info("等待 runner 停止…")
        await runner.stop()
    logger.info("boss-autoapply 后端正在关闭")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="boss-autoapply",
    description="真机端自动筛选 + 半自动投递 Boss 直聘",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: localhost origins only（主防线是 require_auth，CORS 仅辅助）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API 路由注册（全部带写/设备副作用端点均统一 require_auth，AC12）
# ---------------------------------------------------------------------------

from app.api import (  # noqa: E402
    applications,
    config_api,
    jobs,
    logs,
    media,
    messages,
    pipeline,
    session,
)

_API_PREFIX = "/api"

app.include_router(session.router, prefix=_API_PREFIX)
app.include_router(media.router, prefix=_API_PREFIX)
app.include_router(jobs.router, prefix=_API_PREFIX)
app.include_router(applications.router, prefix=_API_PREFIX)
app.include_router(messages.router, prefix=_API_PREFIX)
app.include_router(config_api.router, prefix=_API_PREFIX)
app.include_router(logs.router, prefix=_API_PREFIX)
app.include_router(pipeline.router, prefix=_API_PREFIX)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """无鉴权健康检查 — 仅 localhost bind 访问。"""
    return {
        "status": "ok",
        "bind_host": settings.bind_host,
    }


# ---------------------------------------------------------------------------
# 启动初始化（模块级，确保执行）
# ---------------------------------------------------------------------------
# socketio.ASGIApp(other_asgi_app=app) 不向 FastAPI 转发 lifespan scope，
# 因此 DB 建表 / 崩溃自检 / scrcpy 命名空间注册必须在此同步完成，
# 不能依赖 @asynccontextmanager lifespan（已验证 lifespan 内 register 从未生效）。

def _startup_init() -> None:
    if not settings.terminal_token:
        logger.warning(
            "TERMINAL_TOKEN 未设置：控制端点仅靠 localhost-bind + Origin 保护。"
        )
    from app.db import init_db
    init_db()
    # （已移除 scrcpy 投屏命名空间：PC 微信小程序无需投屏，预览走 /api/media/screenshot）
    # 启动自检：SENDING 残留推人工确认（AC8）
    try:
        from app.pipeline.dispatcher import scan_sending
        stuck = scan_sending()
        if stuck:
            logger.warning("scan_sending: %d 条 SENDING 待人工确认: %s", len(stuck), stuck)
    except Exception as exc:
        logger.warning("scan_sending 出错: %s", exc)


_startup_init()


# ---------------------------------------------------------------------------
# ASGI 组合：Socket.IO 包裹 FastAPI
# ---------------------------------------------------------------------------

asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:asgi_app",
        host=settings.bind_host,
        port=8000,
        reload=False,
        log_level="info",
    )
