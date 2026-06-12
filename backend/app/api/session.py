"""session —— BOSS小程序窗口/会话状态（替代 ms 的 adb devices，鉴权 AC12）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from app.security.auth import require_auth

router = APIRouter(prefix="/session", tags=["session"])


@router.get("", dependencies=[Depends(require_auth)])
async def session_status() -> dict:
    """报告 BOSS直聘 小程序窗口是否就绪（前端据此提示用户在微信中打开）。"""
    from app.desktop import window

    wi = await asyncio.to_thread(window.find_miniprogram_window)
    if wi is None:
        return {"ready": False, "reason": "未找到 BOSS直聘 小程序窗口（请在微信中打开）"}
    return {
        "ready": True,
        "hwnd": wi.hwnd,
        "title": wi.title,
        "rect": {"x": wi.x, "y": wi.y, "w": wi.w, "h": wi.h},
    }
