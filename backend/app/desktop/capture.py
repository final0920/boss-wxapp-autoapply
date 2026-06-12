"""窗口截图 —— 置顶 + 屏幕 DC BitBlt。

G0 实测：直接 PrintWindow 后台 Chromium GPU 窗口会返回空白；先 SetForegroundWindow
触发重绘、再用屏幕 DC BitBlt 截目标矩形可得清晰图（148KB / 9000+ 色）。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes as wt

from PIL import Image

from app.desktop import window as _win

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
_SRCCOPY = 0x00CC0020


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def capture_window(hwnd: int, bring_to_front: bool = True, settle_sec: float = 0.5) -> Image.Image:
    """截取窗口当前像素为 RGB PIL Image。

    bring_to_front：先置顶触发重绘（默认 True；后台 GPU 窗口必需）。
    """
    _win.ensure_dpi_aware()
    if bring_to_front:
        _win.foreground(hwnd)
        time.sleep(settle_sec)
    x, y, w, h = _win.get_rect(hwnd)
    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc_mem, hbmp)
    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, _SRCCOPY)
    bmi = _BMIH()
    bmi.biSize = ctypes.sizeof(bmi)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0
    buf = (ctypes.c_char * (w * h * 4))()
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    return Image.frombytes("RGB", (w, h), bytes(buf), "raw", "BGRX")
