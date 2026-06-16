"""
端点鉴权主防线（AC12 / P0-B）

主防线 = localhost-bind + Bearer token + Origin 校验，统一套到所有带写/设备副作用端点。

用法（FastAPI 依赖注入）：
    from app.security.auth import require_auth
    @router.post("/control/tap")
    async def tap(req: Request, _: None = Depends(require_auth)):
        ...
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
