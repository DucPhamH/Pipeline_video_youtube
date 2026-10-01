"""Cấu hình hạ tầng (env) — khác bảng Settings key-value trong DB."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # translate-service/
DATA_DIR = BASE_DIR / "data"
_DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'db.sqlite3'}"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = _DEFAULT_DATABASE_URL

    @field_validator("database_url", mode="before")
    @classmethod
    def _fallback_to_default_when_blank(cls, v):
        return v or _DEFAULT_DATABASE_URL

    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Crawl public URL để fallback callback khi Work không có callback_url
    # Docker: http://crawl-service:8000 ; local: http://localhost:8090
    crawl_service_url: str = "http://localhost:8090"

    # Token dùng chung giữa các service + frontend (env FOLIO_API_TOKEN). Rỗng
    # = không bật auth (chỉ cảnh báo lúc khởi động) — chỉ dùng trong mạng tin cậy.
    folio_api_token: str = ""

    # Trống = nhà AI nằm trong DB của translate (test, chạy một mình).
    # Có URL = đọc nhà AI từ ai-service khi mở job.
    ai_api_base_url: str = ""

    # Giới hạn upload EPUB/TXT (env TRANSLATE_MAX_UPLOAD_MB) và tổng dung lượng
    # giải nén của EPUB (chặn zip bomb).
    translate_max_upload_mb: int = 50
    translate_max_epub_uncompressed_mb: int = 500


config = AppConfig()
DATA_DIR.mkdir(parents=True, exist_ok=True)
