"""
应用配置：pydantic-settings 从 .env 读取。
缺 GPT_API_KEY 时启动报错（AC14）。
"""
from __future__ import annotations

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    gpt_api_key: str = ""
    gpt_base_url: str = "https://gpt.pkpp.cn/v1"
    gpt_model: str = "gpt-5.5"
    gpt_reasoning: str = "high"

    # Server
    bind_host: str = "127.0.0.1"
    terminal_token: str = ""

    # Database
    database_url: str = "sqlite:///./data/boss_autoapply.db"

    # Rate limits (仅作 RulesConfig 首次缺省填充；运行期以 Config.rules 为权威)
    daily_apply_limit: int = 150
    apply_interval_min: int = 20
    apply_interval_max: int = 90

    # Pipeline
    score_threshold: int = 80

    # Inbox watcher poll interval (seconds)
    inbox_poll_min_sec: int = 120
    inbox_poll_max_sec: int = 300

    # LLM/VLM（httpx 直连；视觉定位/抽取用低推理省时，见 plan §2.5）
    llm_timeout_sec: int = 120
    vlm_reasoning: str = "low"
    vlm_daily_budget: int = 2000  # 每日 VLM 调用上限（成本熔断，M5 接入）

    @model_validator(mode="after")
    def _require_gpt_api_key(self) -> "Settings":
        if not self.gpt_api_key:
            raise ValueError(
                "GPT_API_KEY is required but not set. "
                "Copy .env.example to .env and fill in GPT_API_KEY."
            )
        return self

    @field_validator("bind_host")
    @classmethod
    def _require_token_for_remote(cls, v: str) -> str:
        # 具体的 terminal_token 非空校验在 _require_token_when_remote 中（model_validator）
        return v

    @model_validator(mode="after")
    def _require_token_when_remote(self) -> "Settings":
        # BIND_HOST != 127.0.0.1 时强制 TERMINAL_TOKEN 非空高熵（AC12/P2）
        if self.bind_host != "127.0.0.1" and not self.terminal_token:
            raise ValueError(
                "TERMINAL_TOKEN must be set (non-empty, high-entropy) "
                "when BIND_HOST != 127.0.0.1"
            )
        return self


settings = Settings()
