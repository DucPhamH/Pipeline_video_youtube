"""Domain entities — thuần Python, không phụ thuộc SQLAlchemy."""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field


class WorkStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


class SourceType(str, enum.Enum):
    UPLOAD = "upload"
    CRAWL_HANDOFF = "crawl_handoff"


class VariantStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SegmentStatus(str, enum.Enum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED_CACHE = "skipped_cache"


PROMPT_VERSION = "v1"


@dataclass
class GlossaryTerm:
    id: int | None
    work_id: int
    source_term: str
    target_term: str
    protected: bool = False
    notes: str = ""
    kind: str = ""  # character|place|term|other|""
    # candidate = AI đề xuất qua bảng duyệt tên, CHƯA đưa vào prompt dịch.
    status: str = "approved"


GLOSSARY_KINDS = ("character", "place", "term", "other", "")
GLOSSARY_STATUSES = ("candidate", "approved")


@dataclass
class SkinMapEntry:
    """1 dòng bảng đổi vỏ của variant reskin."""

    id: int | None
    variant_id: int
    original: str
    replacement: str
    kind: str = ""
    locked: bool = False


@dataclass
class Work:
    id: int | None
    title: str
    author: str
    lang_src: str
    lang_tgt: str
    source_type: SourceType
    status: WorkStatus = WorkStatus.READY
    external_id: str | None = None
    callback_url: str | None = None
    # Gate chất lượng (spec 6/B2) — số liệu crawl-service gửi kèm mỗi lần handoff,
    # chỉ để CẢNH BÁO trên UI translate-service; không tự chặn dịch (crawl-service
    # đã có require_cleaned riêng của nó trước khi gọi handoff).
    missing_cleaned: int = 0
    unreviewed_chapters: int = 0
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = field(default_factory=dt.datetime.utcnow)


@dataclass
class ChapterSource:
    id: int | None
    work_id: int
    index: int
    title: str
    text: str
    fingerprint: str


@dataclass
class Variant:
    id: int | None
    work_id: int
    mode: str  # full | pov | audio_cut | style_clone | reskin
    status: VariantStatus
    lang_tgt: str
    mode_params: dict = field(default_factory=dict)
    source_variant_id: int | None = None  # fork từ variant full đã dịch — None nếu mode=full
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)


@dataclass
class Job:
    id: int | None
    variant_id: int
    status: JobStatus
    provider: str
    model: str
    prompt_version: str = PROMPT_VERSION
    error: str | None = None
    base_url: str = ""
    api_key: str = ""
    requires_api_key: bool = True
    # AI provider đã lưu (registry) job này được tạo từ — None nếu job dùng
    # provider/model/key gõ tay trực tiếp (không qua registry). Cho phép
    # resume_job() re-resolve credential MỚI NHẤT của registry thay vì kẹt
    # mãi ở snapshot cũ lúc tạo job (vd user sửa lại key sai trong Settings).
    ai_provider_id: int | None = None
    # Snapshot mọi key của AI (cùng model) lúc tạo job — dùng xoay vòng /
    # failover 429 trong 1 job tuần tự (không cần tick use_all_keys → pool).
    api_keys: list[str] = field(default_factory=list)
    # "single" (1 AI, mặc định) | "pool" (>=2 AI chia nhau dịch song song,
    # round-robin theo chương) | "fallback" (>=2 AI theo thứ tự ưu tiên — AI
    # đầu dùng tới khi lỗi liên tục mới tự chuyển AI kế, không chạy song song).
    ai_mode: str = "single"
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = field(default_factory=dt.datetime.utcnow)


@dataclass
class AiProvider:
    """Kết nối AI đã lưu — user chọn theo id khi start/resume/patch job."""

    id: int | None
    label: str
    kind: str  # openai|claude|gemini|deepseek|groq|mistral|openrouter|xai|qwen|local|mock|custom
    provider: str  # "openai" | "mock" — engine value, suy ra từ kind
    base_url: str = ""
    model: str = ""  # 1 model duy nhất — pattern thật của các tool tương tự
    # (AiNiee/Glossarion) là xoay nhiều KEY cùng 1 model, không xoay theo tên
    # model (thường vẫn tính chung 1 hạn mức nếu cùng 1 key/project) nên bỏ
    # multi-model per-AI, chỉ giữ multi-key.
    api_key: str = ""  # key "chính" — api_keys[0], giữ để tương thích chỗ dùng 1 key
    requires_api_key: bool = True
    # Nhiều API KEY của CÙNG 1 tài khoản/nhà cung cấp (vd nhiều tài khoản free
    # tier Gemini khác nhau) — kiểu AiNiee/Glossarion: xoay vòng nhiều key CÙNG
    # 1 model để né rate-limit thật (mỗi key thường có hạn mức riêng).
    api_keys: list[str] = field(default_factory=list)
    sort_order: int = 0
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = field(default_factory=dt.datetime.utcnow)


@dataclass
class Segment:
    id: int | None
    job_id: int
    chapter_index: int
    status: SegmentStatus
    source_text: str
    output_text: str | None = None
    cache_key: str = ""
    error: str | None = None
    reviewed: bool = False
    slot_index: int = 0  # AI nào trong pool (job_provider_slots) dịch segment này
    # Tóm tắt "trạng thái truyện" LŨY KẾ tính đến hết chương này (quan hệ nhân
    # vật, sự kiện quan trọng, tình tiết chưa giải quyết) — chỉ có khi bật
    # mode_params["track_story_state"]. Chương sau đọc field này của chương
    # TRƯỚC (bất kể slot/model nào dịch) để giữ trí nhớ dài hạn, không chỉ
    # đuôi chương ngay trước như prior_context.
    story_state: str = ""
    # Cảnh báo QA luật rẻ sau khi dịch (xem application/segment_qa.py).
    qa_flags: list[str] = field(default_factory=list)


@dataclass
class JobProviderSlot:
    """1 AI trong pool nhiều-AI-chia-nhau-dịch của 1 Job — snapshot như Job,
    không FK vào AiProviderRepository (đổi/xóa registry sau không ảnh hưởng)."""

    id: int | None
    job_id: int
    slot_index: int
    provider: str
    model: str
    base_url: str = ""
    api_key: str = ""
    requires_api_key: bool = True
    label: str = ""  # nhãn AI để hiển thị UI (vd "Groq", "Local Ollama")
    # Registry AI tạo slot này — resume pool refresh key theo id này.
    ai_provider_id: int | None = None


@dataclass
class TranslationCacheEntry:
    cache_key: str
    output_text: str
