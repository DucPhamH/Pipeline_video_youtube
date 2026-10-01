"""SQLAlchemy ORM."""
import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_.db import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class WorkModel(Base):
    __tablename__ = "works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255), default="")
    lang: Mapped[str] = mapped_column(String(20), default="vi")
    source_type: Mapped[str] = mapped_column(String(30), default="upload")
    cover_path: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    chapters: Mapped[list["ChapterModel"]] = relationship(
        back_populates="work", cascade="all, delete-orphan", order_by="ChapterModel.index"
    )
    readings: Mapped[list["ReadingModel"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
    cast_members: Mapped[list["CastMemberModel"]] = relationship(
        back_populates="work", cascade="all, delete-orphan", order_by="CastMemberModel.id"
    )


class ChapterModel(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, default="")

    work: Mapped["WorkModel"] = relationship(back_populates="chapters")

    __table_args__ = (
        UniqueConstraint("work_id", "index", name="uq_tts_chapter_index"),
        Index("ix_tts_chapter_work_id", "work_id"),
    )


class CastMemberModel(Base):
    __tablename__ = "cast_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    name: Mapped[str] = mapped_column(String(120))
    gender: Mapped[str] = mapped_column(String(20), default="unknown")
    voice: Mapped[str] = mapped_column(String(120), default="")

    work: Mapped["WorkModel"] = relationship(back_populates="cast_members")

    __table_args__ = (Index("ix_tts_cast_work_id", "work_id"),)


class ClonedVoiceModel(Base):
    __tablename__ = "cloned_voices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    audio_path: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class ReadingModel(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    engine: Mapped[str] = mapped_column(String(20), default="edge")
    voice: Mapped[str] = mapped_column(String(120))
    dialogue_voice: Mapped[str] = mapped_column(String(120), default="")
    rate: Mapped[str] = mapped_column(String(20), default="+0%")
    pitch: Mapped[str] = mapped_column(String(20), default="+0Hz")
    volume: Mapped[str] = mapped_column(String(20), default="+0%")
    style: Mapped[str] = mapped_column(String(40), default="")
    device: Mapped[str] = mapped_column(String(10), default="cpu")
    male_voice: Mapped[str] = mapped_column(String(120), default="")
    female_voice: Mapped[str] = mapped_column(String(120), default="")
    use_cast: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    work: Mapped["WorkModel"] = relationship(back_populates="readings")
    jobs: Mapped[list["JobModel"]] = relationship(
        back_populates="reading", cascade="all, delete-orphan"
    )


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reading_id: Mapped[int] = mapped_column(ForeignKey("readings.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    engine: Mapped[str] = mapped_column(String(20), default="edge")
    voice: Mapped[str] = mapped_column(String(120))
    dialogue_voice: Mapped[str] = mapped_column(String(120), default="")
    rate: Mapped[str] = mapped_column(String(20), default="+0%")
    pitch: Mapped[str] = mapped_column(String(20), default="+0Hz")
    volume: Mapped[str] = mapped_column(String(20), default="+0%")
    style: Mapped[str] = mapped_column(String(40), default="")
    device: Mapped[str] = mapped_column(String(10), default="cpu")
    male_voice: Mapped[str] = mapped_column(String(120), default="")
    female_voice: Mapped[str] = mapped_column(String(120), default="")
    use_cast: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    reading: Mapped["ReadingModel"] = relationship(back_populates="jobs")
    segments: Mapped[list["SegmentModel"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="SegmentModel.chapter_index"
    )


class SegmentModel(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    chapter_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    source_text: Mapped[str] = mapped_column(Text, default="")
    cache_key: Mapped[str] = mapped_column(String(64), default="")
    audio_path: Mapped[str] = mapped_column(String(300), default="")
    pieces_json: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["JobModel"] = relationship(back_populates="segments")

    __table_args__ = (Index("ix_tts_segment_job_id", "job_id"),)
