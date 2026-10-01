"""SQLAlchemy ORM — tầng lưu trữ."""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_.db import Base


class WorkModel(Base):
    __tablename__ = "works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255), default="")
    lang_src: Mapped[str] = mapped_column(String(20))
    lang_tgt: Mapped[str] = mapped_column(String(20), default="vi")
    source_type: Mapped[str] = mapped_column(String(30), default="upload")
    status: Mapped[str] = mapped_column(String(20), default="ready")
    callback_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    missing_cleaned: Mapped[int] = mapped_column(Integer, default=0)
    unreviewed_chapters: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    chapters: Mapped[list["ChapterSourceModel"]] = relationship(
        back_populates="work", cascade="all, delete-orphan", order_by="ChapterSourceModel.index"
    )
    variants: Mapped[list["VariantModel"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class ChapterSourceModel(Base):
    __tablename__ = "chapter_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")

    work: Mapped["WorkModel"] = relationship(back_populates="chapters")

    __table_args__ = (
        UniqueConstraint("work_id", "index", name="uq_chapter_source_index"),
        Index("ix_chapter_source_work_id", "work_id"),
    )


class VariantModel(Base):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    mode: Mapped[str] = mapped_column(String(30), default="full")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    lang_tgt: Mapped[str] = mapped_column(String(20), default="vi")
    mode_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("variants.id"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    work: Mapped["WorkModel"] = relationship(back_populates="variants")
    jobs: Mapped[list["JobModel"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_variant_work_id", "work_id"),)


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    model: Mapped[str] = mapped_column(String(100), default="")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    requires_api_key: Mapped[int] = mapped_column(Integer, default=1)
    ai_provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    ai_mode: Mapped[str] = mapped_column(String(20), default="single")
    prompt_version: Mapped[str] = mapped_column(String(20), default="v1")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    variant: Mapped["VariantModel"] = relationship(back_populates="jobs")
    segments: Mapped[list["SegmentModel"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="SegmentModel.chapter_index"
    )
    provider_slots: Mapped[list["JobProviderSlotModel"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobProviderSlotModel.slot_index"
    )

    __table_args__ = (Index("ix_job_variant_id", "variant_id"),)


class JobProviderSlotModel(Base):
    """1 AI trong pool nhiều-AI-chia-nhau-dịch của 1 Job (round-robin theo chương)."""

    __tablename__ = "job_provider_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    slot_index: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    model: Mapped[str] = mapped_column(String(100), default="")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    requires_api_key: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str] = mapped_column(String(100), default="")
    ai_provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped["JobModel"] = relationship(back_populates="provider_slots")

    __table_args__ = (
        UniqueConstraint("job_id", "slot_index", name="uq_job_provider_slot"),
        Index("ix_job_provider_slot_job_id", "job_id"),
    )


class SegmentModel(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    chapter_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    source_text: Mapped[str] = mapped_column(Text, default="")
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_key: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed: Mapped[int] = mapped_column(Integer, default=0)  # 0/1 — SQLite-friendly bool
    slot_index: Mapped[int] = mapped_column(Integer, default=0)
    story_state: Mapped[str] = mapped_column(Text, default="")
    qa_flags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list[str]

    job: Mapped["JobModel"] = relationship(back_populates="segments")

    __table_args__ = (
        UniqueConstraint("job_id", "chapter_index", name="uq_segment_chapter"),
        Index("ix_segment_job_id", "job_id"),
    )


class GlossaryTermModel(Base):
    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    source_term: Mapped[str] = mapped_column(String(255))
    target_term: Mapped[str] = mapped_column(String(255), default="")
    protected: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(String(500), default="")
    # Bảng duyệt tên: character|place|term|other|"" ; candidate chưa đưa vào prompt.
    kind: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(20), default="approved")

    __table_args__ = (
        UniqueConstraint("work_id", "source_term", name="uq_glossary_source"),
        Index("ix_glossary_work_id", "work_id"),
    )


class VariantSkinMapModel(Base):
    """Bảng "đổi vỏ" (mode reskin) — `original` là tên như trong bản FULL."""

    __tablename__ = "variant_skin_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id"))
    original: Mapped[str] = mapped_column(String(255))
    replacement: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(20), default="")
    locked: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("variant_id", "original", name="uq_skin_map_original"),
        Index("ix_skin_map_variant_id", "variant_id"),
    )


class NameApplyBatchModel(Base):
    """1 lần áp tên hàng loạt lên bản đã dịch — lưu để Undo."""

    __tablename__ = "name_apply_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    variant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    changes_json: Mapped[str] = mapped_column(Text, default="[]")
    kind: Mapped[str] = mapped_column(String(20), default="glossary")  # glossary|skin_map

    __table_args__ = (Index("ix_name_apply_batch_work_id", "work_id"),)


class NameApplyRowModel(Base):
    __tablename__ = "name_apply_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("name_apply_batches.id"))
    segment_id: Mapped[int] = mapped_column(Integer)
    old_output: Mapped[str] = mapped_column(Text, default="")
    new_output: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (Index("ix_name_apply_row_batch_id", "batch_id"),)


class TranslationCacheModel(Base):
    __tablename__ = "translation_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    output_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


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
