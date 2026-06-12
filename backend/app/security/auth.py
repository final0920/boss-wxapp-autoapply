"""
端点鉴权主防线（AC12 / P0-B）

主防线 = localhost-bind + Bearer token + Origin 校验，统一套到所有带写/设备副作用端点：
  /control/*  /terminal (WS)  /devices  /config
  scrcpy Socket.IO  SSE 事件流

用法（FastAPI 依赖注入）：
    from app.security.auth import require_auth
    @router.post("/control/tap")
    async def tap(req: Request, _: None = Depends(require_auth)):
        ...

Socket.IO / WebSocket 端点不走 Depends，需手动调用：
    await verify_ws_request(request, token=query_token)
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_localhost_origin(origin: str) -> bool:
    """origin 主机解析为回环地址时返回 True。"""
    after_scheme = origin.split("://", 1)[-1]
    # IPv6 literal: http://[::1]:8080 — extract bracketed address first
    if after_scheme.startswith("["):
        bracket_end = after_scheme.find("]")
        host = after_scheme[1:bracket_end] if bracket_end != -1 else after_scheme
    else:
        host = after_scheme.rsplit(":", 1)[0].strip("/")
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback
    except ValueError:
        host_only = after_scheme.split(":")[0].strip("/")
        return host_only in ("localhost",)


def _token_ok(provided: str) -> bool:
    """与配置 token 进行常量时间比较。"""
    expected = settings.terminal_token
    if not expected:
        # 未配置 token — 仅绑定 localhost 时安全（启动时已校验）
        return True
    return hmac.compare_digest(
        hashlib.sha256(provided.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def _check_origin(request: Request) -> None:
    """拒绝跨域请求（AC12）。"""
    origin = request.headers.get("origin", "")
    if not origin:
        # 无 Origin 头 — 直接/同源请求，放行
        return
    if _is_localhost_origin(origin):
        return
    logger.warning(
        "已拒绝跨域请求 origin=%s path=%s", origin, request.url.path
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cross-origin request rejected",
    )


def _check_peer_ip(request: Request) -> None:
    """L2: TERMINAL_TOKEN 为空时，校验 TCP 对端为回环地址（AC12 纵深）。

    无 token 模式下的第二道防线：即便 Origin 欺骗绕过了 _check_origin，
    TCP 对端也必须是回环地址。
    ASGI scope['client'] 为 (host, port)；部分测试/代理场景不存在，
    此时静默跳过，避免破坏合法配置。
    """
    if settings.terminal_token:
        return  # token 是主防线；无需再做对端检查
    try:
        client = request.scope.get("client")
        if client is None:
            return  # not available (e.g. TestClient) — skip
        peer_ip = client[0]
        addr = ipaddress.ip_address(peer_ip)
        if not addr.is_loopback:
            logger.warning(
                "已拒绝非回环对端 ip=%s path=%s（未配置 token）",
                peer_ip, request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Remote access requires TERMINAL_TOKEN to be configured",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # unexpected — fail open rather than break valid requests


def _check_token(credentials: HTTPAuthorizationCredentials | None) -> None:
    """配置了 token 时，拒绝无效/缺失的 Bearer token 请求。"""
    if not settings.terminal_token:
        return  # 仅 localhost 模式，无需 token
    if credentials is None or not _token_ok(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """FastAPI 依赖 — 鉴权失败时抛 401/403。

    适用于所有带写/设备副作用的端点：
    /control/*, /devices, /config, SSE 事件流。

    校验顺序：Origin → 对端 IP（无 token 模式）→ token。
    """
    _check_origin(request)
    _check_peer_ip(request)
    _check_token(credentials)


# ---------------------------------------------------------------------------
# Manual check for WebSocket / Socket.IO handshake
# ---------------------------------------------------------------------------


async def verify_ws_request(request: Request, token: str | None = None) -> None:
    """在 WS/Socket.IO 连接握手阶段调用。

    WS 升级请求不携带 HTTP Authorization 头；token 通过
    查询参数 `?token=...` 传入。
    """
    _check_origin(request)
    _check_peer_ip(request)
    if settings.terminal_token:
        if token is None or not _token_ok(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing token for WebSocket connection",
            )


# ---------------------------------------------------------------------------
# Socket.IO connect-event auth helper (no exceptions — returns bool)
# ---------------------------------------------------------------------------


def sio_auth_ok(environ: dict) -> bool:
    """校验 Socket.IO connect 事件的鉴权。

    由 socketio 服务器的 connect 处理器调用。
    `environ` 是 python-socketio 传入的 ASGI scope 字典。
    """
    # Origin 校验
    origin = ""
    for k, v in environ.get("headers", []):
        key = k.decode() if isinstance(k, bytes) else k
        if key.lower() == "origin":
            origin = v.decode() if isinstance(v, bytes) else v
            break
    if origin and not _is_localhost_origin(origin):
        logger.warning("Socket.IO 已拒绝跨域连接 origin=%s", origin)
        return False

    # Token 校验
    if settings.terminal_token:
        query_string = environ.get("QUERY_STRING", "")
        if isinstance(query_string, bytes):
            query_string = query_string.decode()
        token = ""
        for part in query_string.split("&"):
            if part.startswith("token="):
                token = part[len("token="):]
                break
        if not _token_ok(token):
            logger.warning("Socket.IO 已拒绝：token 缺失或无效")
            return False

    return True
