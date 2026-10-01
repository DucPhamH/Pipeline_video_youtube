"""Pydantic request/response schemas."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ImportTxtIn(BaseModel):
    title: str
    author: str = ""
    lang_src: str
    lang_tgt: str = "vi"
    text: str


class HandoffChapterIn(BaseModel):
    index: int
    title: str
    text: str
    fingerprint: str = ""
    has_cleaned: bool = True
    reviewed: bool = False
    crawl_chapter_id: int | None = None


class FromCrawlIn(BaseModel):
    """Shape khớp TranslateHandoffOut từ crawl-service."""

    external_id: str
    title: str
    author: str = ""
    lang_src: str
    lang_tgt_hint: str = "vi"
    source_key: str = ""
    source_url: str = ""
    chapters: list[HandoffChapterIn]
    missing_cleaned: int = 0
    unreviewed: int = 0
    callback_url: str | None = None


class ChapterSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    index: int
    title: str
    fingerprint: str
    text_preview: str = ""


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_id: int
    mode: str
    status: str
    lang_tgt: str
    mode_params: dict = Field(default_factory=dict)
    source_variant_id: int | None = None
    latest_job_id: int | None = None


class VariantCreateIn(BaseModel):
    mode: str = "full"
    mode_params: dict = Field(default_factory=dict)
    lang_tgt: str | None = None


class VariantCloneIn(BaseModel):
    mode: str | None = None
    mode_params: dict | None = None
    lang_tgt: str | None = None


class StyleProfileOut(BaseModel):
    id: str
    label: str
    instruction: str


class WorkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None = None
    title: str
    author: str
    lang_src: str
    lang_tgt: str
    source_type: str
    status: str
    missing_cleaned: int = 0
    unreviewed_chapters: int = 0
    chapters: list[ChapterSourceOut] = Field(default_factory=list)
    variants: list[VariantOut] = Field(default_factory=list)


class WorkListOut(BaseModel):
    items: list[WorkOut]


class FromCrawlOut(WorkOut):
    created: bool = False
    changed_chapter_indices: list[int] = Field(default_factory=list)


class InboxItemOut(BaseModel):
    work_id: int
    work_title: str
    variant_id: int
    mode: str
    variant_status: str
    job_id: int | None = None
    job_status: str | None = None
    unreviewed: int = 0


class InboxOut(BaseModel):
    running: list[InboxItemOut] = Field(default_factory=list)
    needs_review: list[InboxItemOut] = Field(default_factory=list)
    ready_export: list[InboxItemOut] = Field(default_factory=list)


class JobProviderSlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot_index: int
    label: str
    provider: str
    model: str
    requires_api_key: bool
    has_api_key: bool = False


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    status: str
    provider: str
    model: str
    base_url: str = ""
    has_api_key: bool = False
    api_key_hint: str = ""
    prompt_version: str
    error: str | None = None
    done_segments: int = 0
    total_segments: int = 0
    failed_segments: int = 0
    # Số segment bị QA luật rẻ gắn cờ (xem SegmentOut.qa_flags).
    flagged_segments: int = 0
    current_chapter: int | None = None
    ai_provider_id: int | None = None
    ai_mode: str = "single"
    current_slot_index: int | None = None
    provider_slots: list[JobProviderSlotOut] = Field(default_factory=list)


class AiSelectionIn(BaseModel):
    """1 AI đã lưu cho job này.

    - `model` (tuỳ chọn): model CHO JOB NÀY — Settings chỉ giữ model mặc định;
      không gửi thì dùng `AiProvider.model`. Snapshot vào job/slot lúc start.
    - `use_all_keys`: nhiều key CÙNG model đó (kiểu AiNiee/Glossarion) — FE gửi
      cờ, server đọc key từ registry (FE không có literal key).
    """

    ai_provider_id: int
    model: str | None = None
    # Chỉ dùng ở tầng application (vd gọi trực tiếp `enqueue_job` trong test/
    # script) khi caller ĐÃ biết literal key — API/FE không bao giờ gửi field
    # này vì key là secret, FE chỉ có hint bị che, không có giá trị thật.
    api_keys: list[str] | None = None
    # FE dùng cờ này thay vì `api_keys` ở trên: true -> lấy TẤT CẢ key đã lưu
    # của AI này (đọc server-side từ registry) làm nhiều slot xoay theo KEY,
    # CÙNG model đã chọn ở trên.
    use_all_keys: bool = False


class ProviderConfigIn(BaseModel):
    """Config provider theo job — không truyền field → inherit job/settings."""

    provider: str | None = None  # mock | openai
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    ai_provider_id: int | None = None  # tham chiếu AI đã lưu trong /ai-providers
    ai_provider_ids: list[int] | None = None  # >=2 -> nhiều AI (xem ai_mode)
    # Mỗi lựa chọn: 1 AI + (tuỳ chọn) model override + (tuỳ chọn) xoay nhiều key.
    # Tổng slot >=2 -> pool/fallback. Ưu tiên hơn ai_provider_ids nếu có.
    ai_selections: list[AiSelectionIn] | None = None
    ai_mode: str = "pool"  # "pool" (chia song song) | "fallback" (dự phòng tuần tự)
    requires_api_key: bool | None = None


class JobStartIn(ProviderConfigIn):
    pass


class JobResumeIn(ProviderConfigIn):
    pass


class JobProviderPatchIn(ProviderConfigIn):
    pass


# Backward alias
JobModelPatchIn = JobProviderPatchIn


class ModelsOut(BaseModel):
    default: str
    suggested: list[str] = Field(default_factory=list)
    default_provider: str = "mock"
    default_base_url: str = ""
    has_default_api_key: bool = False
    suggested_base_urls: list[dict] = Field(default_factory=list)


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    chapter_index: int
    status: str
    cache_key: str
    error: str | None = None
    output_preview: str = ""
    reviewed: bool = False
    qa_flags: list[str] = Field(default_factory=list)


class SegmentDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    chapter_index: int
    status: str
    source_text: str
    output_text: str | None = None
    error: str | None = None
    reviewed: bool = False
    qa_flags: list[str] = Field(default_factory=list)


class SegmentPutIn(BaseModel):
    output_text: str
    reviewed: bool = True


class GlossaryTermIn(BaseModel):
    source_term: str
    target_term: str = ""
    protected: bool = False
    notes: str = ""
    kind: str | None = None  # character|place|term|other|"" — None: giữ nguyên (PUT)
    status: str | None = None  # candidate|approved — None: approved (POST) / giữ nguyên (PUT)


class GlossaryTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_id: int
    source_term: str
    target_term: str
    protected: bool
    notes: str = ""
    kind: str = ""
    status: str = "approved"


# --- Bảng duyệt tên ---------------------------------------------------------


class NameOutputHitOut(BaseModel):
    variant_id: int
    mode: str
    segments: int


class NameItemOut(BaseModel):
    id: int
    source_term: str
    target_term: str
    kind: str = ""
    status: str = "approved"
    notes: str = ""
    protected: bool = False
    source_chapter_count: int = 0
    output_hits: list[NameOutputHitOut] = Field(default_factory=list)


class NamesExtractIn(BaseModel):
    provider_id: int | None = None
    sample_chapters: int = 12  # tối đa 40 (kẹp phía server)


class NamesExtractOut(BaseModel):
    added: int
    terms: list[NameItemOut]


class NamesApproveIn(BaseModel):
    term_ids: list[int]


class NameApplyChangeIn(BaseModel):
    term_id: int
    new_target: str


class NamesApplyIn(BaseModel):
    changes: list[NameApplyChangeIn]
    variant_ids: list[int] | None = None
    dry_run: bool = False


class NameApplyPerTermOut(BaseModel):
    term_id: int
    old_target: str
    new_target: str
    segments: int
    replacements: int


class NameApplySampleOut(BaseModel):
    segment_id: int
    variant_id: int
    chapter_index: int
    title: str = ""
    before: str
    after: str


class NameApplyOut(BaseModel):
    batch_id: int | None = None
    total_replacements: int
    per_term: list[NameApplyPerTermOut]
    samples: list[NameApplySampleOut]


class NameBatchChangeOut(BaseModel):
    old: str
    new: str


class NameBatchOut(BaseModel):
    id: int
    created_at: dt.datetime
    kind: str
    variant_id: int | None = None
    changes: list[NameBatchChangeOut]
    segments: int


class NameUndoOut(BaseModel):
    restored: int
    skipped: int


# --- Bảng đổi vỏ (reskin) ------------------------------------------------------


class SkinMapRowOut(BaseModel):
    id: int
    original: str
    replacement: str
    kind: str = ""
    locked: bool = False


class SkinMapGenerateIn(BaseModel):
    provider_id: int | None = None
    overwrite: bool = False


class SkinMapRowIn(BaseModel):
    original: str
    replacement: str
    kind: str | None = None


class SkinMapRowPatchIn(BaseModel):
    replacement: str | None = None
    kind: str | None = None
    locked: bool | None = None


class SkinMapApplyChangeIn(BaseModel):
    row_id: int
    new_replacement: str


class SkinMapApplyIn(BaseModel):
    changes: list[SkinMapApplyChangeIn]
    dry_run: bool = False


class EstimateOut(BaseModel):
    variant_id: int | None = None
    work_id: int | None = None
    chapter_count: int
    char_count: int
    estimated_tokens: int
    usd_per_1k_tokens: float
    estimated_usd: float
    budget_usd: float
    over_budget: bool


class SettingsOut(BaseModel):
    values: dict


class SettingsPutIn(BaseModel):
    values: dict


class AiProviderIn(BaseModel):
    label: str
    kind: str = "custom"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    # >=2 key của CÙNG kết nối này (vd nhiều tài khoản free tier Gemini khác
    # nhau) — job có thể chọn xoay theo key thay vì theo model để né rate-limit
    # (mỗi key thường có hạn mức riêng). Rỗng -> chỉ dùng `api_key`.
    api_keys: list[str] = Field(default_factory=list)
    requires_api_key: bool = True


class AiProviderAddKeyIn(BaseModel):
    """Thêm 1 key vào danh sách api_keys — server tự đọc list hiện có rồi
    append, client không cần biết/gửi lại các key cũ (key là secret, chỉ có
    hint bị che ở phía client, không thể round-trip nguyên vẹn)."""

    api_key: str


class AiProviderPatchIn(BaseModel):
    label: str | None = None
    kind: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None  # None = giữ nguyên; "" = xoá
    api_keys: list[str] | None = None  # None = giữ nguyên; [] = xoá hết key phụ
    requires_api_key: bool | None = None


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    provider_id: int
    messages: list[ChatMessageIn]


class ChatOut(BaseModel):
    content: str


class AiProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    kind: str
    provider: str
    base_url: str
    model: str
    requires_api_key: bool
    has_api_key: bool = False
    api_key_hint: str = ""
    # 1 hint/key theo đúng thứ tự api_keys đã lưu (không bao giờ trả key thật).
    api_key_hints: list[str] = Field(default_factory=list)
    key_count: int = 1
    sort_order: int = 0
