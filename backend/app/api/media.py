"""media —— BOSS小程序窗口截图端点（替代 ms 的 adb 截图，鉴权 AC12）。"""
from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.security.auth import require_auth

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/screenshot", dependencies=[Depends(require_auth)])
async def screenshot() -> Response:
    """返回 BOSS小程序窗口 PNG 截图（前端预览用）。"""

    def _grab() -> bytes:
        from app.desktop import capture, window

        wi = window.find_miniprogram_window()
        if wi is None:
            raise RuntimeError("未找到 BOSS小程序窗口")
        img = capture.capture_window(wi.hwnd)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    try:
        png = await asyncio.to_thread(_grab)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(e)) from e
    return Response(content=png, media_type="image/png")
