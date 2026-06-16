"""cdp —— CDP/Frida 注入感知+动作层（替代 desktop/OCR）。

WMPFDebugger 边车开启标准 CDP（ws://127.0.0.1:62000）；本层连它：
- 读：渲染层同源 iframe DOM（精确，零 OCR）
- 写：Input.dispatchTouchEvent 真实触摸（触发小程序 bindtap）
"""
from app.cdp.client import CDPClient, CDPError, get_cdp

__all__ = ["CDPClient", "CDPError", "get_cdp"]
