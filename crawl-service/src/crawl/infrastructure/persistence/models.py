"""SQLAlchemy ORM — tầng lưu trữ, KHÁC với domain/entities.py (thuần Python).
repositories.py chịu trách nhiệm map 2 chiều giữa ORM model và domain entity."""
import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_.db import Base


class GenreModel(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(50))
    genre_key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    list_url: Mapped[str] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Trạng thái lần "Quét ngay"/job lịch gần nhất — LƯU LẠI để FE biết đang
    # chạy hay đã xong dù có tải lại trang (crawl-service.md mục 9.2).
    last_run_status: Mapped[str] = mapped_column(String(20), default="idle")
    last_run_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_discovered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_rejected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_messages: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("source_key", "genre_key", name="uq_genre_source_key"),)


class NovelModel(Base):
    __tablename__ = "novels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255), default="")
    cover_url: Mapped[str] = mapped_column(String(500), default="")
    content_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    source_key: Mapped[str] = mapped_column(String(50))
    source_url: Mapped[str] = mapped_column(String(500))
    genre_id: Mapped[int | None] = mapped_column(ForeignKey("genres.id"), nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    last_chapter_index: Mapped[int] = mapped_column(Integer, default=0)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    total_chapters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="discovered")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    chapters: Mapped[list["ChapterModel"]] = relationship(
        back_populates="novel", cascade="all, delete-orphan", order_by="ChapterModel.chapter_index"
    )

    __table_args__ = (
        UniqueConstraint("source_key", "source_url", name="uq_novel_source"),
        Index("ix_novel_lifecycle_status", "lifecycle_status"),
        Index("ix_novel_genre_id", "genre_id"),
        Index("ix_novel_content_fingerprint", "content_fingerprint"),
    )


class ChapterModel(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    novel_id: Mapped[int] = mapped_column(ForeignKey("novels.id"))
    chapter_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(String(500))
    raw_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_for_translate: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    novel: Mapped["NovelModel"] = relationship(back_populates="chapters")

    __table_args__ = (
        UniqueConstraint("novel_id", "chapter_index", name="uq_chapter_index"),
        Index("ix_chapter_novel_id", "novel_id"),
        Index("ix_chapter_status", "status"),
    )
