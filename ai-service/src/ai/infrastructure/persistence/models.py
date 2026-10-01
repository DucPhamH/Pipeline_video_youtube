"""Nhà AI đã lưu. Key chỉ nằm ở service này."""
import datetime as dt

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from platform_.db import Base


class AiProviderModel(Base):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30), default="custom")
    provider: Mapped[str] = mapped_column(String(20), default="openai")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    api_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    requires_api_key: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


class AiUsageModel(Base):
    """Một lượt gọi model thành công. Token lấy từ trường usage của API, không có thì 0."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(Integer, index=True)
    model: Mapped[str] = mapped_column(String(100), default="")
    caller: Mapped[str] = mapped_column(String(30), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)
