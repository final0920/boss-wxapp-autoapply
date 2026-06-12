"""窗口定位 —— 找到/置顶 BOSS直聘 微信小程序窗口。

G0 实测：小程序窗口是 WeChatAppEx.exe 进程拥有的可见 `Chrome_WidgetWin_*`
（竖屏，如 643x1181）。优先按"WeChatAppEx 拥有 + Chromium 类名"匹配，标题兜底。
DPI：本机 150% 缩放，进程须 PerMonitorV2 感知，GetWindowRect 才返回物理像素。
"""
from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes as wt
from dataclasses import dataclass

user32 = ctypes.windll.user32
_dpi_set = False
_CREATE_NO_WINDOW = 0x08000000


def ensure_dpi_aware() -> None:
    """进程级 DPI 感知（PerMonitorV2 优先），幂等。"""
    global _dpi_set
    if _dpi_set:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    _dpi_set = True


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    x: int
    y: int
    w: int
    h: int


def _wechat_appex_pids() -> set[int]:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process WeChatAppEx -ErrorAction SilentlyContinue).Id -join ','"],
            text=True, creationflags=_CREATE_NO_WINDOW,
        ).strip()
        return {int(x) for x in out.split(",") if x.strip().isdigit()}
    except Exception:
        return set()


def find_miniprogram_window(keywords: tuple[str, ...] = ("BOSS", "直聘")) -> WindowInfo | None:
    """返回最匹配的 BOSS小程序窗口；未找到返回 None。"""
    ensure_dpi_aware()
    pids = _wechat_appex_pids()
    hits: list[tuple[WindowInfo, bool, bool]] = []  # (info, owned, titled)

    EP = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        tb = ctypes.create_unicode_buffer(512); user32.GetWindowTextW(hwnd, tb, 512)
        cb = ctypes.create_unicode_buffer(256); user32.GetClassNameW(hwnd, cb, 256)
        pid = wt.DWORD(0); user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        r = wt.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if w < 50 or h < 50:
            return True
        owned = pid.value in pids
        titled = any(k.upper() in tb.value.upper() for k in keywords)
        if (owned and cb.value.startswith("Chrome_WidgetWin")) or titled:
            hits.append((WindowInfo(int(hwnd), tb.value, r.left, r.top, w, h), owned, titled))
        return True

    user32.EnumWindows(EP(_cb), 0)
    if not hits:
        return None
    # 排序键：owned → titled → 竖屏 → 面积
    best = max(hits, key=lambda t: (t[1], t[2], t[0].h > t[0].w, t[0].w * t[0].h))
    return best[0]


def foreground(hwnd: int) -> None:
    """恢复并置顶窗口（截图/点击前调用，触发小程序重绘）。"""
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


def get_rect(hwnd: int) -> tuple[int, int, int, int]:
    """窗口物理像素矩形 (x, y, w, h)。"""
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top
