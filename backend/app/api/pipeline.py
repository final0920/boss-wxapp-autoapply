"""pipeline — runner 控制面（run/stop/status）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.pipeline.runner import runner
from app.security.auth import require_auth

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", dependencies=[Depends(require_auth)])
async def run_pipeline(body: dict | None = None) -> dict:
    """启动 runner。幂等：已有活跃 Task 返回 409（防双驱动，A11）。

    body 可选 {"serial": "..."}；缺省取第一台 USB 在线真机。
    """
    serial = (body or {}).get("serial", "")
    if not serial:
        from app.desktop import window
        wi = await asyncio.to_thread(window.find_miniprogram_window)
        if wi is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="未找到 BOSS小程序窗口（请在微信中打开该小程序）",
            )
        serial = "wxapp"
    started = runner.start(serial)
    if not started:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="runner 已在运行（重复启动被拒绝）",
        )
    return {"ok": True, "serial": serial}


@router.post("/stop", dependencies=[Depends(require_auth)])
async def stop_pipeline() -> dict:
    """停止 runner（等待当前卡片动作收尾，Task 真停）。"""
    await runner.stop()
    return {"ok": True, "state": runner.state}


@router.get("/status", dependencies=[Depends(require_auth)])
async def pipeline_status() -> dict:
    """runner 状态：state/子态/paused_reason/统计/今日配额。"""
    return await runner.status()
