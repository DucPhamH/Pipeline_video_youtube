"""Settings key-value dùng chung — thêm setting = thêm dòng SEED_DEFAULTS."""
import datetime as dt
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_.db import Base

SEED_DEFAULTS: dict[str, Any] = {
    "translate.openai_base_url": "https://api.deepseek.com/v1",
    "translate.openai_api_key": "",
    "translate.openai_model": "deepseek-chat",
    "translate.provider": "mock",  # mock | openai
    "translate.usd_per_1k_tokens": 0.14,  # DeepSeek-ish default; user chỉnh
    "translate.budget_usd_per_job": 0.0,  # 0 = không cap
}


class SettingsModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


def seed_missing(db: Session, defaults: dict[str, Any]) -> None:
    existing = {row.key for row in db.query(SettingsModel.key).all()}
    for key, value in defaults.items():
        if key not in existing:
            db.add(SettingsModel(key=key, value=value))
    db.commit()


def seed_defaults(db: Session) -> None:
    seed_missing(db, SEED_DEFAULTS)


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(SettingsModel, key)
    if row is None:
        return SEED_DEFAULTS.get(key, default)
    return row.value


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(SettingsModel, key)
    if row is None:
        db.add(SettingsModel(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_all(db: Session) -> dict[str, Any]:
    merged = dict(SEED_DEFAULTS)
    for row in db.query(SettingsModel).all():
        merged[row.key] = row.value
    return merged
