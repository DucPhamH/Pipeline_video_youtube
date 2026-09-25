// Khớp 1-1 với Pydantic schemas ở crawl-service (crawl/api/schemas.py).
// Đổi schema bên backend thì sửa ở đây theo — không có công cụ tự sinh
// type, nên đây là chỗ DUY NHẤT cần đồng bộ tay khi backend đổi field.

export type LifecycleStatus =
  | "discovered"
  | "crawling"
  | "fully_crawled"
  | "translating"
  | "ready_for_video"
  | "produced"
  | "rejected"
  | "error"

export type SiteAccessKind = "free" | "session_optional" | "session_required"

export type SiteRegion = "china" | "japan" | "korea" | "vietnam" | "taiwan"

export interface Site {
  key: string
  name: string
  access_kind: SiteAccessKind
  region: SiteRegion
}

export type SiteAccessFilter = SiteAccessKind | "needs_session" | "all"

export type SiteRegionFilter = SiteRegion | "all"

export interface SiteListParams {
  search?: string
  accessKind?: SiteAccessFilter
  region?: SiteRegionFilter
  limit?: number
  offset?: number
}

export interface SiteListResult {
  items: Site[]
  total: number
}

export type GenreRunStatus = "idle" | "running" | "done" | "error" | "cancelled"

export interface Genre {
  id: number
  source_key: string
  genre_key: string
  label: string
  list_url: string
  enabled: boolean
  // Mọi option của 1 site nằm CHUNG 1 danh sách PHẲNG — chỉ những
  // thể loại/search THẬT trên site (catalog GENRE_SEEDS), không có field
  // nhóm cặp / Hot tự chế.
  last_run_status: GenreRunStatus
  last_run_started_at: string | null
  last_run_finished_at: string | null
  last_run_discovered: number | null
  last_run_rejected: number | null
  last_run_errors: number | null
  last_run_messages: string | null
}

/** Snapshot live khi đang quét — khớp GenreProgressOut backend. */
export interface GenreProgress {
  task_id: string
  kind: string
  label: string
  phase: string
  page: number
  max_pages: number
  discovered: number
  rejected: number
  errors: number
  synced: number
  scan_window: number
  novel_title: string
  chapter_index: number
  chapter_total: number
  message: string
}

export interface GenreProgressResult {
  progress: GenreProgress | null
}

export interface GenreListParams {
  sourceKey?: string
  search?: string
  enabled?: boolean
  lastRunStatus?: GenreRunStatus
  limit?: number
  offset?: number
}

export interface GenreListResult {
  items: Genre[]
  total: number
}

export interface Novel {
  id: number
  title: string
  source_key: string
  source_url: string
  genre_id: number | null
  is_manual: boolean
  total_chapters: number | null
  last_chapter_index: number
  lifecycle_status: LifecycleStatus
  error_message: string | null
  author?: string
  cover_url?: string
}

export interface NovelListParams {
  status?: string
  sourceKey?: string
  search?: string
  /** true = tab Thêm URL; false = tab Quét nhiều; omit = tất cả */
  isManual?: boolean
  /** Lọc truyện phát hiện từ 1 thể loại quét cụ thể */
  genreId?: number
  limit?: number
  offset?: number
}

export interface NovelListResult {
  items: Novel[]
  total: number
}

export interface Chapter {
  id: number
  chapter_index: number
  title: string
  status: string
  error_message: string | null
  reviewed: boolean
  has_cleaned?: boolean
}

export interface ChapterContent {
  chapter_id: number
  success: boolean
  content: string | null
  reviewed: boolean
  error: string | null
  has_cleaned?: boolean
  content_source?: "raw" | "cleaned"
  raw_content?: string | null
  cleaned_content?: string | null
}

export interface ChapterRetryResult {
  chapter_id: number
  success: boolean
  status: string
  error: string | null
  novel_completed: boolean
}

export interface SmoothNovelResult {
  novel_id: number
  success: boolean
  chapters_smoothed: number
  chapters_skipped: number
  removed_lines: number
  chapter_ids: number[]
  error: string | null
}

export interface NovelExportStatus {
  crawled: number
  cleaned: number
  reviewed: number
  can_export_workbook: boolean
  can_export_txt?: boolean
  can_export_epub?: boolean
  can_export_bundle?: boolean
}

export interface ReviewAllResult {
  success: boolean
  chapters_reviewed: number
  chapters_skipped: number
  error: string | null
}

export interface ChapterListParams {
  status?: string
  search?: string
  reviewed?: boolean
  has_cleaned?: boolean
  limit?: number
  offset?: number
}

export interface ChapterListResult {
  items: Chapter[]
  total: number
}

export interface CrawlNovelResult {
  novel_id: number
  chapters_crawled: number
  success: boolean
  error: string | null
}

export interface RetryErrorsResult {
  queued: number
  skipped: number
  novel_ids: number[]
}

export interface SettingsValues {
  values: Record<string, number | string | boolean>
}

export interface SiteSession {
  source_key: string
  configured: boolean
  cookie_names: string[]
  cookie_header: string
  required_cookies: string[]
  missing_required_cookies: string[]
}

export interface SiteSessionProbe {
  ok: boolean
  final_url: string | null
  http_status: number | null
  page_title: string | null
  looks_blocked: boolean
  message: string
  cookie_configured: boolean
  missing_required_cookies: string[]
}

export type DryRunMode = "genre" | "chapters" | "content"

export interface DryRunPreviewItem {
  title?: string
  url?: string
  latest_chapter_title?: string
  index?: number
}

export interface DryRunResult {
  ok: boolean
  mode: DryRunMode
  preview: DryRunPreviewItem[] | null
  content_preview: string | null
  content_length: number | null
  validation_passed: boolean | null
  error: string | null
}
