"""Application settings, loaded from `.env` (never hard-coded)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- card reading ---
    # "anthropic" (cloud, paid, accurate) or "ollama" (local, free).
    vision_backend: str = Field(default="anthropic", alias="VISION_BACKEND")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    vision_model: str = Field(default="claude-haiku-4-5", alias="VISION_MODEL")

    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    # Must be a model whose Ollama capabilities include "vision" -- a text
    # model answers an image request with HTTP 400.
    ollama_model: str = Field(default="qwen3.5:0.8b", alias="OLLAMA_MODEL")
    ollama_think: bool = Field(default=False, alias="OLLAMA_THINK")
    ollama_timeout: float = Field(default=180.0, alias="OLLAMA_TIMEOUT")

    watch_dir: Path = Field(
        default=Path.home() / "Pictures" / "Screenshots", alias="WATCH_DIR"
    )
    watch_extensions: str = Field(default=".png,.jpg,.jpeg", alias="WATCH_EXTENSIONS")

    # Clipboard capture: Win+Shift+S a card and it is read without saving a file.
    clipboard_enabled: bool = Field(default=True, alias="CLIPBOARD_ENABLED")
    clipboard_poll_interval: float = Field(default=1.2, alias="CLIPBOARD_POLL_INTERVAL")

    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8027, alias="PORT")

    price_providers: str = Field(default="futwiz,futgg", alias="PRICE_PROVIDERS")
    price_cache_ttl: int = Field(default=420, alias="PRICE_CACHE_TTL")
    browser_min_interval: float = Field(default=6.0, alias="BROWSER_MIN_INTERVAL")
    browser_challenge_timeout: float = Field(
        default=25.0, alias="BROWSER_CHALLENGE_TIMEOUT"
    )
    # Measured: headless clears FUTWIZ once and is then blocked on every
    # later load; a normal (headful) window clears each one in ~1.3 s.
    browser_headless: bool = Field(default=False, alias="BROWSER_HEADLESS")
    # Park the window off-screen so it does not steal focus while you play.
    browser_offscreen: bool = Field(default=True, alias="BROWSER_OFFSCREEN")

    ea_tax_rate: float = Field(default=0.05, alias="EA_TAX_RATE")

    db_path: Path = Field(default=PROJECT_ROOT / "data" / "fc27.sqlite3")
    inbox_dir: Path = Field(default=PROJECT_ROOT / "data" / "inbox")
    browser_profile_dir: Path = Field(default=PROJECT_ROOT / "data" / "browser-profile")

    @field_validator("watch_dir", mode="before")
    @classmethod
    def _expand(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value.strip().strip('"')).expanduser()
        return value

    @property
    def extensions(self) -> tuple[str, ...]:
        return tuple(
            e.strip().lower() if e.strip().startswith(".") else f".{e.strip().lower()}"
            for e in self.watch_extensions.split(",")
            if e.strip()
        )

    @property
    def provider_order(self) -> tuple[str, ...]:
        return tuple(p.strip().lower() for p in self.price_providers.split(",") if p.strip())


settings = Settings()
