"""Cấu hình hạ tầng (env)."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # ai-service/
DATA_DIR = BASE_DIR / "data"
_DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'db.sqlite3'}"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = _DEFAULT_DATABASE_URL
    folio_api_token: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def _fallback_to_default_when_blank(cls, v):
        return v or _DEFAULT_DATABASE_URL

    @field_validator("folio_api_token", mode="before")
    @classmethod
    def _strip_token(cls, v):
        return (v or "").strip()

    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


config = AppConfig()
DATA_DIR.mkdir(parents=True, exist_ok=True)
