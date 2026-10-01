"""Pydantic request/response — tầng trình diễn, KHÁC domain/entities.py.

`model_config = ConfigDict(from_attributes=True)` cho phép trả thẳng domain
entity (dataclass) từ router — Pydantic tự đọc field qua getattr, không cần
tự tay build dict như trước (đỡ 1 tầng chuyển đổi thủ công dễ lệch field
khi entity đổi)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SiteOut(BaseModel):
    """1 dòng trong trang "Danh sách site" (mục 9.0) — chỉ site KHÔNG phải
    `is_test` (SourcePort.is_test) mới xuất hiện ở đây."""

    key: str
    name: str
    # free | session_optional | session_required — xem site_access.py
    access_kind: Literal["free", "session_optional", "session_required"]
    # china | japan | korea | vietnam | taiwan — xem site_regions.py
    region: Literal["china", "japan", "korea", "vietnam", "taiwan"]


class SiteListOut(BaseModel):
    items: list[SiteOut]
    total: int


class GenreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_key: str
    genre_key: str
    label: str
    list_url: str
    enabled: bool
    # Mọi option của 1 site (kể cả "Hot nhất") nằm CHUNG 1 danh sách PHẲNG,
    # không có "kind" hay "family_key" nhóm cặp gì cả (sửa 17/9/2026, 2 lần)
    # — mỗi dòng ở đây mirror thẳng 1 URL liệt kê/xếp hạng có thật trên site.
    # GenreRunStatus kế thừa str -> serialize thẳng ("idle"/"running"/"done"/"error"/"cancelled")
    last_run_status: str
    last_run_started_at: datetime | None
    last_run_finished_at: datetime | None
    last_run_discovered: int | None
    last_run_rejected: int | None
    last_run_errors: int | None
    last_run_messages: str | None


class GenreListOut(BaseModel):
    items: list[GenreOut]
    total: int


class GenreToggleIn(BaseModel):
    enabled: bool


class GenreProgressOut(BaseModel):
    """Snapshot live khi genre đang quét — FE poll trong lúc last_run_status=running."""

    task_id: str
    kind: str
    label: str
    phase: str
    page: int = 0
    max_pages: int = 0
    discovered: int = 0
    rejected: int = 0
    errors: int = 0
    synced: int = 0
    scan_window: int = 0
    novel_title: str = ""
    chapter_index: int = 0
    chapter_total: int = 0
    message: str = ""


class NovelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_key: str
    source_url: str
    genre_id: int | None
    is_manual: bool
    total_chapters: int | None
    last_chapter_index: int = 0
    lifecycle_status: str  # NovelLifecycle kế thừa str -> serialize thẳng được
    error_message: str | None
    author: str = ""
    cover_url: str = ""
    # Additive — đếm theo trạng thái Chapter (1 query GROUP BY cho cả trang).
    crawled_chapters: int = 0
    failed_chapters: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TranslateHandoffChapterOut(BaseModel):
    """1 chương trong payload handoff → translate-service."""

    index: int
    title: str
    text: str
    fingerprint: str
    has_cleaned: bool
    reviewed: bool
    crawl_chapter_id: int
    # Thứ tự đọc (vị trí TOC, fallback index) — `index` giữ làm định danh ổn định.
    order: int | None = None


class TranslateHandoffOut(BaseModel):
    """Contract Phase 0 — Translate kéo hoặc FE POST lại /works/from-crawl."""

    external_id: str
    title: str
    author: str
    lang_src: str
    lang_tgt_hint: str = "vi"
    source_key: str
    source_url: str
    chapters: list[TranslateHandoffChapterOut]
    missing_cleaned: int = 0
    unreviewed: int = 0


class TranslateLifecycleIn(BaseModel):
    """Callback từ translate-service → cập nhật lifecycle novel."""

    status: str  # translating | ready_for_video | failed
    message: str | None = None


class SendToTranslateIn(BaseModel):
    require_cleaned: bool = True
    start_job: bool = True


class SendToTranslateOut(BaseModel):
    novel_id: int
    lifecycle_status: str
    work_id: int
    variant_id: int
    job_id: int | None = None
    missing_cleaned: int = 0
    unreviewed: int = 0
    translate_path: str = ""  # FE deep-link gợi ý
    # Cảnh báo không chặn (novel đang lỗi / còn chương failed / thiếu chương).
    warnings: list[str] = []


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_index: int
    title: str
    status: str
    error_message: str | None
    reviewed: bool
    has_cleaned: bool = False
    toc_order: int | None = None


class ChapterListOut(BaseModel):
    items: list[ChapterOut]
    total: int


class NovelListOut(BaseModel):
    """Bọc thêm `total` (không áp limit/offset) để FE tính số trang — mục 9.5."""

    items: list[NovelOut]
    total: int


class ChapterContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapter_id: int
    success: bool
    content: str | None = None
    reviewed: bool = False
    error: str | None = None
    has_cleaned: bool = False
    content_source: str = "raw"
    raw_content: str | None = None
    cleaned_content: str | None = None


class ChapterRetryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapter_id: int
    success: bool
    status: str
    error: str | None = None
    novel_completed: bool = False


class SmoothNovelIn(BaseModel):
    """`chapter_ids=null/[]` = tất cả chương crawled; có list = chỉ những id đó."""

    chapter_ids: list[int] | None = None
    # true = làm mượt cả chương đã review/sửa tay (ghi đè bản sửa).
    force: bool = False


class SmoothNovelOut(BaseModel):
    novel_id: int
    success: bool
    chapters_smoothed: int = 0
    chapters_skipped: int = 0
    chapters_protected: int = 0
    removed_lines: int = 0
    chapter_ids: list[int] = []
    error: str | None = None


class DeleteOut(BaseModel):
    success: bool
    error: str | None = None


class NovelExportStatusOut(BaseModel):
    crawled: int = 0
    cleaned: int = 0
    reviewed: int = 0
    can_export_workbook: bool = False
    can_export_txt: bool = False
    can_export_epub: bool = False
    can_export_bundle: bool = False


class BatchExportIn(BaseModel):
    novel_ids: list[int]
    format: str = "bundle"  # xlsx | txt | epub | bundle


class ReviewAllOut(BaseModel):
    success: bool
    chapters_reviewed: int = 0
    chapters_skipped: int = 0
    error: str | None = None


class ChapterContentIn(BaseModel):
    content: str


class AddNovelIn(BaseModel):
    source_key: str
    url: str
    # Giữ field để FE cũ không lỗi — bị bỏ qua: thêm tay luôn crawl all,
    # không áp filter settings (chỉ "Quét ngay" mới dùng settings).
    force: bool = True


class CrawlNovelResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    novel_id: int
    chapters_crawled: int
    success: bool
    error: str | None


class RetryErrorsIn(BaseModel):
    """Retry hàng loạt novel đang error (thường lỗ VIP) sau khi cập nhật cookie."""

    source_key: str
    genre_id: int | None = None
    is_manual: bool | None = None
    limit: int = 100


class RetryErrorsOut(BaseModel):
    queued: int
    skipped: int
    novel_ids: list[int]


class DryRunIn(BaseModel):
    source_key: str
    url: str
    mode: Literal["genre", "chapters", "content"]


class DryRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool
    mode: str
    preview: list[dict] | None = None
    content_preview: str | None = None
    content_length: int | None = None
    validation_passed: bool | None = None
    error: str | None = None


class SettingsOut(BaseModel):
    values: dict


class SettingsPatchIn(BaseModel):
    values: dict


class SiteSessionOut(BaseModel):
    source_key: str
    configured: bool
    cookie_names: list[str]
    # KHÔNG bao giờ trả giá trị cookie thật — luôn rỗng (giữ field cho FE cũ);
    # xem has_cookie + cookie_hint.
    cookie_header: str = ""
    has_cookie: bool = False
    cookie_hint: str = ""
    required_cookies: list[str] = []
    missing_required_cookies: list[str] = []


class SiteSessionIn(BaseModel):
    """Chuỗi cookie copy từ trình duyệt: `name=value; name2=value2`."""

    cookie_header: str = ""


class SiteSessionProbeOut(BaseModel):
    ok: bool
    final_url: str | None = None
    http_status: int | None = None
    page_title: str | None = None
    looks_blocked: bool = False
    message: str
    cookie_configured: bool = False
    missing_required_cookies: list[str] = []


class FollowIn(BaseModel):
    auto_translate: bool = False
    auto_audio: bool = False
    voice_preset: str = "nam_ke"


class FollowOut(BaseModel):
    novel_id: int
    title: str
    lifecycle_status: str
    total_chapters: int | None = None
    auto_translate: bool
    auto_audio: bool = False
    voice_preset: str = "nam_ke"
    tts_work_id: int | None = None
    last_checked_at: datetime | None = None
    last_new_chapters: int = 0
    last_error: str | None = None
    checking: bool = False


class FollowListOut(BaseModel):
    items: list[FollowOut]


class PipelineIn(BaseModel):
    voice_preset: str = "nam_ke"
    engine: str = "edge"


class PipelineOut(BaseModel):
    novel_id: int
    title: str
    stage: str
    voice_preset: str
    engine: str
    translate_work_id: int | None = None
    tts_work_id: int | None = None
    error: str | None = None


class PipelineListOut(BaseModel):
    items: list[PipelineOut]
