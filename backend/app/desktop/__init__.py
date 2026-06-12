"""desktop —— 非侵入桌面控制层（替代 ms 的 adb/ + scrcpy/）。

window:  定位/置顶 BOSS直聘 微信小程序窗口（WeChatAppEx 的 Chromium 窗口）
capture: 置顶 + 屏幕 DC BitBlt 截图（G0 实测对 GPU 窗口可靠）
input:   归一化坐标 → DPI 物理像素 → SendInput 点击/滚动
"""
from app.desktop.capture import capture_window
from app.desktop.input import click_norm, norm_to_screen, scroll
from app.desktop.window import (
    WindowInfo,
    ensure_dpi_aware,
    find_miniprogram_window,
    foreground,
    get_rect,
)

__all__ = [
    "WindowInfo",
    "find_miniprogram_window",
    "foreground",
    "get_rect",
    "ensure_dpi_aware",
    "capture_window",
    "click_norm",
    "scroll",
    "norm_to_screen",
]
