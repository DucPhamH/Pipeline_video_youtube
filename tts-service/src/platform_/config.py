"""Cấu hình hạ tầng (env)."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # tts-service/
DATA_DIR = BASE_DIR / "data"
_DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'db.sqlite3'}"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = _DEFAULT_DATABASE_URL
    audio_dir: str = ""
    ai_api_base_url: str = "http://127.0.0.1:8013"
    vieneu_cache_dir: str = ""
    # Token dùng chung giữa các service. Trống = không kiểm tra (chỉ cảnh báo lúc khởi động).
    folio_api_token: str = ""
    # Giới hạn file TXT / EPUB tải lên (MB).
    tts_max_upload_mb: int = 50

    @field_validator("database_url", mode="before")
    @classmethod
    def _fallback_to_default_when_blank(cls, v):
        return v or _DEFAULT_DATABASE_URL

    @field_validator("ai_api_base_url", mode="before")
    @classmethod
    def _ai_base(cls, v):
        return (v or "http://127.0.0.1:8013").rstrip("/")

    @field_validator("folio_api_token", mode="before")
    @classmethod
    def _strip_token(cls, v):
        return (v or "").strip()

    @field_validator("tts_max_upload_mb", mode="before")
    @classmethod
    def _upload_mb(cls, v):
        return v if v not in (None, "") else 50

    def max_upload_bytes(self) -> int:
        return max(int(self.tts_max_upload_mb), 1) * 1024 * 1024

    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    def resolved_audio_dir(self) -> Path:
        path = Path(self.audio_dir) if self.audio_dir.strip() else DATA_DIR / "audio"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolved_vieneu_dir(self) -> Path:
        path = Path(self.vieneu_cache_dir) if self.vieneu_cache_dir.strip() else DATA_DIR / "vieneu"
        path.mkdir(parents=True, exist_ok=True)
        return path


config = AppConfig()
DATA_DIR.mkdir(parents=True, exist_ok=True)
