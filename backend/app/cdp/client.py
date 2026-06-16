"""CDP 客户端 —— 连 WMPFDebugger 代理(默认 ws://127.0.0.1:62000)驱动小程序。

M0 实测（见 plan §2.5）：
- 读：CDP 连渲染层根帧；职位内容在同源子 iframe，经 `iframe.contentDocument` 直读（精确，零 OCR）。
- 写：`Input.dispatchTouchEvent`(touchStart+touchEnd) 于根视口坐标触发 bindtap；鼠标事件无效。

驱动方法在 runner 的 asyncio.to_thread 线程里调用，故本客户端对外是**同步** API：
内部用独立线程跑一个 asyncio 事件循环 + websockets 持久连接，命令经
run_coroutine_threadsafe 提交、按 id 匹配响应。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Optional

import websockets

from app.config import settings

logger = logging.getLogger(__name__)


class CDPError(Exception):
    pass


class CDPClient:
    def __init__(self, url: Optional[str] = None) -> None:
        self._url = url or settings.cdp_url
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="cdp-loop", daemon=True)
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._started = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _aconnect(self) -> None:
        self._ws = await websockets.connect(self._url, max_size=None, ping_interval=None,
                                            open_timeout=settings.cdp_connect_timeout_sec)
        asyncio.ensure_future(self._reader())

    async def _reader(self) -> None:
        try:
            assert self._ws is not None
            async for raw in self._ws:
                msg = json.loads(raw)
                mid = msg.get("id")
                if mid in self._pending:
                    fut = self._pending.pop(mid)
                    if not fut.done():
                        fut.set_result(msg)
        except Exception as e:  # noqa: BLE001
            logger.warning("CDP reader 结束: %s", e)
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(CDPError("connection closed"))
            self._pending.clear()

    def connect(self) -> None:
        if not self._started:
            self._thread.start()
            self._started = True
        asyncio.run_coroutine_threadsafe(self._aconnect(), self._loop).result(
            timeout=settings.cdp_connect_timeout_sec + 3)
        self.cmd("Runtime.enable")

    def is_connected(self) -> bool:
        if self._ws is None:
            return False
        try:
            return self._ws.close_code is None  # None 表示仍打开（新旧 websockets 通用）
        except Exception:  # noqa: BLE001
            return False

    def ensure_connected(self) -> None:
        """断连自愈：未连或已断则重连。"""
        try:
            if self.is_connected():
                return
        except Exception:  # noqa: BLE001
            pass
        logger.info("CDP 重连…")
        self.connect()

    def close(self) -> None:
        try:
            if self._ws is not None:
                asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop).result(timeout=3)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 命令 / 求值 / 触摸
    # ------------------------------------------------------------------
    async def _acmd(self, method: str, params: dict, timeout: float) -> dict:
        self._id += 1
        i = self._id
        fut = self._loop.create_future()
        self._pending[i] = fut
        assert self._ws is not None
        await self._ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        return await asyncio.wait_for(fut, timeout)

    def cmd(self, method: str, params: Optional[dict] = None, timeout: float = 20.0) -> dict:
        fut = asyncio.run_coroutine_threadsafe(self._acmd(method, params or {}, timeout), self._loop)
        return fut.result(timeout=timeout + 5)

    def evaluate(self, expression: str, timeout: float = 20.0) -> Any:
        """在根帧上下文求值，返回 JS 值（returnByValue）。JS 抛错则 raise CDPError。"""
        r = self.cmd("Runtime.evaluate",
                     {"expression": expression, "returnByValue": True, "awaitPromise": True}, timeout)
        res = r.get("result", {})
        if "exceptionDetails" in res:
            raise CDPError("JS 异常: " + json.dumps(res["exceptionDetails"], ensure_ascii=False)[:300])
        if "error" in r:
            raise CDPError("CDP 错误: " + json.dumps(r["error"], ensure_ascii=False)[:200])
        return res.get("result", {}).get("value")

    def touch(self, x: int, y: int) -> None:
        """于根视口坐标 (x,y) 注入一次真实触摸点击（M0 验证可触发 bindtap）。"""
        self.cmd("Input.dispatchTouchEvent", {"type": "touchStart",
                                              "touchPoints": [{"x": int(x), "y": int(y)}]})
        self.cmd("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    def swipe(self, x1: int, y1: int, x2: int, y2: int, steps: int = 8) -> None:
        """真实滑动手势（touchStart→多段 touchMove→touchEnd）。小程序 scroll-view
        不吃 scrollTop，必须用手势触发滚动 + 懒加载。"""
        self.cmd("Input.dispatchTouchEvent", {"type": "touchStart",
                                              "touchPoints": [{"x": int(x1), "y": int(y1)}]})
        for i in range(1, steps + 1):
            xi = int(x1 + (x2 - x1) * i / steps)
            yi = int(y1 + (y2 - y1) * i / steps)
            self.cmd("Input.dispatchTouchEvent", {"type": "touchMove",
                                                  "touchPoints": [{"x": xi, "y": yi}]})
        self.cmd("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


# 进程内单例（runner/driver 共用）
_client: Optional[CDPClient] = None
_lock = threading.Lock()


def get_cdp() -> CDPClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = CDPClient()
    return _client
