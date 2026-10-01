from pydantic import BaseModel, Field


class ImportTxtIn(BaseModel):
    title: str
    author: str = ""
    lang: str = "vi"
    text: str


class ChapterIn(BaseModel):
    index: int
    title: str = ""
    text: str


class FromTranslateIn(BaseModel):
    title: str
    author: str = ""
    lang: str = "vi"
    external_id: str
    chapters: list[ChapterIn]


class ReadingIn(BaseModel):
    engine: str = "edge"
    voice: str = ""
    dialogue_voice: str = ""
    rate: str = ""
    pitch: str = ""
    volume: str = ""
    style: str = ""
    preset_id: str = ""
    male_voice: str = ""
    female_voice: str = ""
    use_cast: bool = False
    provider_id: int | None = None
    device: str = "cpu"


class CastMemberIn(BaseModel):
    name: str
    gender: str = "unknown"
    voice: str = ""


class CastPutIn(BaseModel):
    members: list[CastMemberIn] = Field(default_factory=list)


class DetectIn(BaseModel):
    provider_id: int


class CastMemberOut(BaseModel):
    id: int
    name: str
    gender: str
    voice: str


class CloneOut(BaseModel):
    id: str
    label: str


class EnginesOut(BaseModel):
    edge: bool = True
    mock: bool = True
    vieneu: bool = False
    vieneu_gpu: bool = False


class PreviewIn(BaseModel):
    engine: str = "edge"
    voice: str
    lang: str = "vi"
    dialogue_voice: str = ""
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    style: str = ""
    device: str = "cpu"


class VoiceOut(BaseModel):
    id: str
    label: str
    locale: str
    gender: str
    styles: list[str] = Field(default_factory=list)


class VoicesOut(BaseModel):
    sample: str
    voices: list[VoiceOut]


class PresetOut(BaseModel):
    id: str
    voice: str
    dialogue_voice: str
    rate: str
    pitch: str
    volume: str
    style: str


class ChapterOut(BaseModel):
    index: int
    title: str


class JobOut(BaseModel):
    id: int
    reading_id: int
    status: str
    engine: str
    voice: str
    dialogue_voice: str
    rate: str
    pitch: str
    volume: str
    style: str
    male_voice: str = ""
    female_voice: str = ""
    use_cast: bool = False
    device: str = "cpu"
    error: str | None = None
    done_segments: int = 0
    total_segments: int = 0
    failed_segments: int = 0
    # Chương không có chữ — đã tính trong done_segments; tách riêng để hiển thị.
    skipped_segments: int = 0


class ActiveJobOut(BaseModel):
    """Job đang xếp hàng/đang chạy — cho widget "Running now" của frontend."""

    job_id: int
    reading_id: int
    work_id: int
    work_title: str
    status: str
    done_segments: int = 0
    total_segments: int = 0
    skipped_segments: int = 0


class ReadingOut(BaseModel):
    id: int
    work_id: int
    engine: str
    voice: str
    dialogue_voice: str
    rate: str
    pitch: str
    volume: str
    style: str
    male_voice: str = ""
    female_voice: str = ""
    use_cast: bool = False
    device: str = "cpu"
    status: str
    latest_job: JobOut | None = None


class WorkOut(BaseModel):
    id: int
    title: str
    author: str
    lang: str
    source_type: str
    external_id: str | None = None
    chapters: list[ChapterOut] = Field(default_factory=list)
    readings: list[ReadingOut] = Field(default_factory=list)
    cast: list[CastMemberOut] = Field(default_factory=list)
    created: bool = True


class WorkListItem(BaseModel):
    id: int
    title: str
    author: str
    lang: str
    source_type: str
    chapter_count: int
    # Tóm tắt job mới nhất của reading mới nhất (None = chưa đọc lần nào).
    latest_status: str | None = None
    latest_done: int = 0
    latest_total: int = 0


class WorkListOut(BaseModel):
    items: list[WorkListItem]


class SegmentOut(BaseModel):
    id: int
    job_id: int
    chapter_index: int
    title: str
    status: str
    error: str | None = None
    has_audio: bool = False
