"""Cấu hình hạ tầng (env-based) — KHÁC với bảng Settings key-value trong DB
(xem settings_store.py). Cái này là config để KHỞI ĐỘNG app (đường dẫn DB,
API key...), không chỉnh được qua UI lúc app đang chạy.
"""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # crawl-service/
DATA_DIR = BASE_DIR / "data"
_DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'db.sqlite3'}"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    # SQLite mặc định (free, zero-setup). Đổi sang Postgres chỉ cần đổi
    # chuỗi này (vd "postgresql+psycopg://user:pass@host/db"), không đổi code
    # — xem docs/platform-and-licensing.md mục 3.
    database_url: str = _DEFAULT_DATABASE_URL

    @field_validator("database_url", mode="before")
    @classmethod
    def _fallback_to_default_when_blank(cls, v):
        # .env để trống DATABASE_URL= (chuỗi rỗng) vẫn phải fallback về
        # SQLite mặc định — pydantic-settings mặc định coi "biến env có tồn
        # tại, dù rỗng" là override, KHÔNG tự fallback field default. Bug
        # thật đã bắt được lúc chạy Docker (env_file nạp DATABASE_URL= rỗng
        # -> SQLAlchemy crash "Could not parse SQLAlchemy URL from string ''").
        return v or _DEFAULT_DATABASE_URL

    # --- License (self-host, xem docs/platform-and-licensing.md mục 1) ---
    license_key: str = ""

    # --- CORS cho React FE (chạy port khác, vd 5173/3000) ---
    cors_allow_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Crawl runtime ---
    raw_dir: Path = DATA_DIR / "raw"
    cleaned_dir: Path = DATA_DIR / "cleaned"
    fixtures_dir: Path = DATA_DIR / "fixtures"
    request_delay_sec: float = 1.0

    # Proxy (vn thường cần exit VN) — xem proxy_pool.py / .env.example.
    # Giá trị cũng đọc trực tiếp từ env trong proxy_pool (CRAWL_HTTP_PROXY…).
    crawl_http_proxy: str = ""
    crawl_proxy_file: str = ""
    crawl_proxy_vn: str = ""
    crawl_proxy_jp: str = ""
    crawl_proxy_kr: str = ""

    # --- Scheduler ---
    crawl_hour: int = 6
    crawl_minute: int = 0
    crawl_enabled: bool = True

    # --- Translate handoff (P2) ---
    # Docker: http://translate-service:8000 ; local: http://localhost:8010
    # (8001 thường bị service khác chiếm trên máy dev)
    translate_service_url: str = "http://localhost:8010"
    # URL crawl tự publish để translate callback (Docker: http://crawl-service:8000)
    crawl_public_url: str = "http://localhost:8090"


config = AppConfig()

for _dir in (config.raw_dir, config.cleaned_dir):
    _dir.mkdir(parents=True, exist_ok=True)
