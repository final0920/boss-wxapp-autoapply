"""
应用配置：pydantic-settings 从 .env 读取。
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

    # CDP（WMPFDebugger 代理；M0 验证见 plan §2.5）
    cdp_url: str = "ws://127.0.0.1:62000"
    cdp_connect_timeout_sec: int = 10

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
