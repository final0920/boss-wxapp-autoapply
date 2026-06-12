"""模拟输入 —— 归一化坐标(0-1000) → DPI 物理像素 → SetCursorPos + mouse_event。

G0 实测：归一化坐标按 `screen = 窗口原点 + 归一化/1000 × 窗口物理尺寸` 映射（PerMonitorV2
DPI-aware）后点击命中；点位应指向标题/薪资/按钮区，勿落在技能标签或 HR 行。
"""
from __future__ import annotations

import ctypes
import time

from app.desktop import window as _win

user32 = ctypes.windll.user32
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_WHEEL = 0x0800


def norm_to_screen(hwnd: int, cx: int, cy: int) -> tuple[int, int]:
    """窗口内归一化坐标(0-1000) → 屏幕物理像素。"""
    x, y, w, h = _win.get_rect(hwnd)
    return x + int(cx / 1000 * w), y + int(cy / 1000 * h)


def click_norm(hwnd: int, cx: int, cy: int, settle_sec: float = 1.2) -> None:
    """点击窗口内归一化坐标处（先置顶）。"""
    _win.ensure_dpi_aware()
    _win.foreground(hwnd)
    time.sleep(0.3)
    sx, sy = norm_to_screen(hwnd, cx, cy)
    user32.SetCursorPos(sx, sy)
    time.sleep(0.15)
    user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(settle_sec)


def scroll(hwnd: int, clicks: int = -3) -> None:
    """在窗口中心滚动滚轮（clicks<0 向下/加载更多）。"""
    _win.ensure_dpi_aware()
    _win.foreground(hwnd)
    x, y, w, h = _win.get_rect(hwnd)
    user32.SetCursorPos(x + w // 2, y + h // 2)
    time.sleep(0.1)
    user32.mouse_event(_MOUSEEVENTF_WHEEL, 0, 0, clicks * 120, 0)
    time.sleep(0.8)
