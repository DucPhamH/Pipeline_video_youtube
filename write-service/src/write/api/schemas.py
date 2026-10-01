from pydantic import BaseModel, Field


class StoryCharacterIn(BaseModel):
    name: str
    role: str = ""


class StoryCreateIn(BaseModel):
    title: str
    premise: str
    ending: str = ""
    chapter_count: int = Field(ge=4, le=40)
    provider_id: int
    characters: list[StoryCharacterIn] = Field(default_factory=list, max_length=8)


class StoryPatchIn(BaseModel):
    title: str | None = None
    premise: str | None = None
    ending: str | None = None
    chapter_count: int | None = Field(default=None, ge=4, le=40)
    provider_id: int | None = None
    characters: list[StoryCharacterIn] | None = Field(default=None, max_length=8)


class StoryChapterPatchIn(BaseModel):
    title: str | None = None
    beat: str | None = None
    text: str | None = None


class StoryWriteIn(BaseModel):
    force: bool = False


class StoryCharacterOut(BaseModel):
    name: str
    role: str


class StoryChapterOut(BaseModel):
    index: int
    title: str
    beat: str
    text: str


class StoryOut(BaseModel):
    id: int
    title: str
    premise: str
    ending: str
    chapter_count: int
    provider_id: int | None
    status: str
    write_error: str
    characters: list[StoryCharacterOut]
    chapters: list[StoryChapterOut]


class StoryListItemOut(BaseModel):
    id: int
    title: str
    chapter_count: int
    filled_count: int
    status: str


class StoryListOut(BaseModel):
    items: list[StoryListItemOut]
