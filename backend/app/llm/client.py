"""LLM 客户端 —— gpt-5.5（gpt.pkpp.cn）httpx 直连封装（文本 + 多模态）。

为什么用 httpx 而非 openai SDK（G0 实测，见 .omc/plans/boss-wxapp-autoapply-plan.md §2.5）：
gpt.pkpp.cn 前置 Cloudflare WAF 会拦 openai SDK 的 X-Stainless-* 头 / `OpenAI/Python`
UA，返回 403 "Your request was blocked."；裸 httpx POST 同请求正常 200。

接口与旧版一致：chat()/locate()/get_client()，screener 等调用方零改。
新增 vision_json()：发送截图 + 指令，返回解析后的 JSON（视觉抽取用，低推理省时）。
Authorization/key 不写入日志；临时错误（429/5xx）自动重试，其余快速失败。
"""
from __future__ import annotations

import base64
import json
import logging
import time
from io import BytesIO
from typing import Any

import httpx
from PIL.Image import Image

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2.0  # 秒；每次翻倍
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMError(Exception):
    """LLM 调用错误（非重试错误或重试耗尽）。"""


class LLMClient:
    """gpt-5.5 httpx 封装。文本用 settings.gpt_reasoning(high)，视觉用 settings.vlm_reasoning(low)。"""

    def __init__(self) -> None:
        self._url = settings.gpt_base_url.rstrip("/") + "/chat/completions"
        self._key = settings.gpt_api_key
        self._model = settings.gpt_model
        self._reasoning = settings.gpt_reasoning
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=float(settings.llm_timeout_sec), write=30.0, pool=10.0)
        )

    def _post(self, body: dict[str, Any]) -> str:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        last: LLMError | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                r = self._client.post(self._url, headers=headers, content=json.dumps(body))
            except httpx.RequestError as exc:
                last = LLMError(type(exc).__name__)
                time.sleep(_RETRY_BACKOFF_BASE ** attempt)
                continue
            if r.status_code == 200:
                return (r.json()["choices"][0]["message"]["content"] or "").strip()
            if r.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                logger.warning("LLM 临时错误 status=%s，第 %d/%d 次重试",
                               r.status_code, attempt + 1, _MAX_RETRIES)
                last = LLMError(f"status={r.status_code}")
                time.sleep(_RETRY_BACKOFF_BASE ** attempt)
                continue
            raise LLMError(f"status={r.status_code} body={r.text[:200]}")
        raise last or LLMError("unknown")

    # ------------------------------------------------------------------
    # 文本
    # ------------------------------------------------------------------
    def chat(self, messages: list[dict[str, Any]], json_mode: bool = False,
             reasoning: str | None = None) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "reasoning_effort": reasoning or self._reasoning,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return self._post(body)

    # ------------------------------------------------------------------
    # 视觉
    # ------------------------------------------------------------------
    def locate(self, image: Image, instruction: str) -> tuple[int, int]:
        """截图 + 指令 → (x, y) 归一化 0-1000。"""
        messages = [{"role": "user", "content": [
            {"type": "text", "text": instruction + '\n\n只输出 JSON：{"x": <0-1000>, "y": <0-1000>}'},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_pil_to_b64(image)}"}},
        ]}]
        return _parse_coords(self.chat(messages, json_mode=True, reasoning=settings.vlm_reasoning))

    def vision_json(self, image: Image, instruction: str) -> Any:
        """截图 + 指令 → 解析后的 JSON（视觉抽取，低推理）。"""
        messages = [{"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_pil_to_b64(image)}"}},
        ]}]
        return json.loads(self.chat(messages, json_mode=True, reasoning=settings.vlm_reasoning))


_client_instance: LLMClient | None = None


def get_client() -> LLMClient:
    """返回共享的 LLMClient 单例。"""
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _pil_to_b64(image: Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _parse_coords(raw: str) -> tuple[int, int]:
    try:
        data = json.loads(raw)
        x, y = int(data["x"]), int(data["y"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise LLMError(f"无法解析坐标: {raw!r}") from exc
    if not (0 <= x <= 1000 and 0 <= y <= 1000):
        raise LLMError(f"坐标越界: x={x}, y={y}")
    return x, y
