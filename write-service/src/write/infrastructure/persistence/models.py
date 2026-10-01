"""SQLAlchemy ORM — truyện người dùng tự viết."""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_.db import Base


class StoryModel(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    premise: Mapped[str] = mapped_column(Text, default="")
    ending: Mapped[str] = mapped_column(Text, default="")
    chapter_count: Mapped[int] = mapped_column(Integer, default=8)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    write_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    characters: Mapped[list["StoryCharacterModel"]] = relationship(
        back_populates="story",
        cascade="all, delete-orphan",
        order_by="StoryCharacterModel.position",
    )
    chapters: Mapped[list["StoryChapterModel"]] = relationship(
        back_populates="story",
        cascade="all, delete-orphan",
        order_by="StoryChapterModel.index",
    )


class StoryCharacterModel(Base):
    __tablename__ = "story_characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(200), default="")

    story: Mapped["StoryModel"] = relationship(back_populates="characters")


class StoryChapterModel(Base):
    __tablename__ = "story_chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"))
    index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255), default="")
    beat: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")

    story: Mapped["StoryModel"] = relationship(back_populates="chapters")

    __table_args__ = (UniqueConstraint("story_id", "index", name="uq_story_chapter_index"),)
