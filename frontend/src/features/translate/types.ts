export type Work = {
  id: number
  external_id: string | null
  title: string
  author: string
  lang_src: string
  lang_tgt: string
  source_type: string
  status: string
  missing_cleaned: number
  unreviewed_chapters: number
  chapters: ChapterSource[]
  variants: Variant[]
}

export type WorkList = { items: Work[] }

export type ChapterSource = {
  id: number
  index: number
  title: string
  fingerprint: string
  text_preview: string
}

export type Variant = {
  id: number
  work_id: number
  mode: string
  status: string
  lang_tgt: string
  mode_params: Record<string, unknown>
  source_variant_id: number | null
  latest_job_id: number | null
}

export type StyleProfile = {
  id: string
  label: string
  instruction: string
}

export type JobProviderSlot = {
  slot_index: number
  label: string
  provider: string
  model: string
  requires_api_key: boolean
  has_api_key: boolean
}

export type Job = {
  id: number
  variant_id: number
  status: string
  provider: string
  model: string
  base_url?: string
  has_api_key?: boolean
  api_key_hint?: string
  requires_api_key?: boolean
  prompt_version: string
  error: string | null
  done_segments: number
  total_segments: number
  failed_segments: number
  current_chapter?: number | null
  ai_provider_id?: number | null
  ai_mode?: string
  current_slot_index?: number | null
  provider_slots?: JobProviderSlot[]
  /** Số segment bị QA gắn cờ (backend mới — có thể không có). */
  flagged_segments?: number
}

export type ProviderConfig = {
  provider?: string
  model?: string
  base_url?: string
  api_key?: string
  ai_provider_id?: number | null
  /** >=2 -> pool hoặc fallback (xem ai_mode) */
  ai_provider_ids?: number[]
  /** >=1 AI, mỗi AI có thể mang nhiều KEY (né rate-limit) -> tổng slot >=2 thì dùng pool/fallback. Ưu tiên hơn ai_provider_ids. */
  ai_selections?: AiSelection[]
  /** "pool" (chia song song, mặc định) | "fallback" (dự phòng tuần tự — AI đầu tạch thì tự chuyển AI kế) */
  ai_mode?: 'pool' | 'fallback'
  requires_api_key?: boolean
}

export type AiProvider = {
  id: number
  label: string
  kind: string
  provider: string
  base_url: string
  model: string
  requires_api_key: boolean
  has_api_key: boolean
  api_key_hint: string
  /** 1 hint/key theo thứ tự đã lưu (không bao giờ có key thật). */
  api_key_hints: string[]
  key_count: number
  sort_order: number
}

export type AiProviderInput = {
  label: string
  kind: string
  base_url?: string
  model?: string
  api_key?: string
  /** Chỉ dùng lúc TẠO MỚI (key chưa bị che, gõ tay thoải mái). Sửa key sau
   * này dùng addAiProviderKey/deleteAiProviderKey — không gửi lại api_keys
   * qua PUT vì key là secret, client chỉ có hint, không round-trip được. */
  api_keys?: string[]
  requires_api_key?: boolean
}

export type AiSelection = {
  ai_provider_id: number
  /** Model cho job này — bỏ trống thì dùng model mặc định của AI trong Settings. */
  model?: string
  /** true -> lấy TẤT CẢ key đã lưu của AI này (server tự đọc registry — FE
   * không biết/không gửi giá trị key thật, chỉ có hint bị che). Kiểu AiNiee/
   * Glossarion: nhiều key CÙNG model đã chọn né rate-limit. */
  use_all_keys?: boolean
}

export type ModelsInfo = {
  default: string
  suggested: string[]
  default_provider: string
  default_base_url: string
  has_default_api_key: boolean
  suggested_base_urls: { label: string; url: string }[]
}

export type ProviderProfile = {
  id: string
  label: string
  provider: string
  model: string
  base_url: string
  api_key: string
}

export type Segment = {
  id: number
  job_id: number
  chapter_index: number
  status: string
  cache_key: string
  error: string | null
  output_preview: string
  reviewed: boolean
  /** Cờ QA — xem QA_FLAGS trong errorText.ts. */
  qa_flags?: string[]
}

export type SegmentDetail = {
  id: number
  job_id: number
  chapter_index: number
  status: string
  source_text: string
  output_text: string | null
  error: string | null
  reviewed: boolean
  qa_flags?: string[]
}

export type NameKind = "character" | "place" | "term" | "other" | ""
export type NameStatus = "candidate" | "approved"

export type GlossaryTerm = {
  id: number
  work_id: number
  source_term: string
  target_term: string
  protected: boolean
  notes: string
  kind?: NameKind
  status?: NameStatus
}

export type GlossaryTermInput = {
  source_term: string
  target_term?: string
  protected?: boolean
  notes?: string
  kind?: NameKind
  status?: NameStatus
}

export type NameOutputHit = { variant_id: number; mode: string; segments: number }

export type NameItem = {
  id: number
  source_term: string
  target_term: string
  kind: NameKind
  status: NameStatus
  notes: string
  protected: boolean
  source_chapter_count: number
  output_hits: NameOutputHit[]
}

export type NameExtractResult = { added: number; terms: NameItem[] }

export type RenamePerTerm = {
  term_id?: number
  row_id?: number
  old_target: string
  new_target: string
  segments: number
  replacements: number
}

export type RenameSample = {
  segment_id: number
  variant_id: number
  chapter_index: number
  title: string
  before: string
  after: string
}

/** Kết quả POST names/apply và variants/{id}/skin-map/apply (dry_run hoặc thật). */
export type RenameResult = {
  batch_id: number | null
  total_replacements: number
  per_term: RenamePerTerm[]
  samples: RenameSample[]
}

export type RenameBatch = {
  id: number
  created_at: string
  kind: "glossary" | "skin_map"
  variant_id: number | null
  changes: { old: string; new: string }[]
  segments: number
}

export type UndoResult = { restored: number; skipped: number }

export type SkinMapRow = {
  id: number
  original: string
  replacement: string
  kind: string
  locked: boolean
}

export type Estimate = {
  variant_id?: number | null
  work_id?: number | null
  chapter_count: number
  char_count: number
  estimated_tokens: number
  usd_per_1k_tokens: number
  estimated_usd: number
  budget_usd: number
  over_budget: boolean
}

export type SettingsValues = { values: Record<string, unknown> }

export type InboxItem = {
  work_id: number
  work_title: string
  variant_id: number
  mode: string
  variant_status: string
  job_id: number | null
  job_status: string | null
  unreviewed?: number
}

export type Inbox = {
  running: InboxItem[]
  needs_review: InboxItem[]
  ready_export: InboxItem[]
}
