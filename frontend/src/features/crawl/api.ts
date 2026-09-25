import { api } from "../../api/client"
import type {
  ChapterContent,
  ChapterRetryResult,
  CrawlNovelResult,
  DryRunMode,
  DryRunResult,
  Genre,
  Novel,
  ChapterListParams,
  ChapterListResult,
  GenreListParams,
  GenreListResult,
  GenreProgressResult,
  NovelListParams,
  NovelListResult,
  NovelExportStatus,
  RetryErrorsResult,
  ReviewAllResult,
  SiteListParams,
  SiteListResult,
  SettingsValues,
  SiteSession,
  SiteSessionProbe,
  SmoothNovelResult,
} from "../../api/types"

const BASE = "/api/crawl"

// Khớp platform_/settings_store.py per_site_key() — setting riêng từng site
// lưu dưới key "crawl.<key>.<source_key>" (mục 9.0).
export function perSiteSettingKey(key: string, sourceKey: string): string {
  return `crawl.${key}.${sourceKey}`
}

// Toàn bộ gọi API của feature Crawl nằm ở đây — component không tự ghép
// URL/path, dễ đổi endpoint mà không phải sửa nhiều nơi.
export const crawlApi = {
  // Trang "Danh sách site" (mục 9.0) — chỉ site thật, không có demo_local.
  listSites: (params: SiteListParams = {}) => {
    const q = new URLSearchParams()
    if (params.search) q.set("search", params.search)
    if (params.accessKind && params.accessKind !== "all") {
      q.set("access_kind", params.accessKind)
    }
    if (params.region && params.region !== "all") {
      q.set("region", params.region)
    }
    q.set("limit", String(params.limit ?? 20))
    q.set("offset", String(params.offset ?? 0))
    return api.get<SiteListResult>(`${BASE}/sites?${q.toString()}`)
  },

  listGenres: (params: GenreListParams = {}) => {
    const q = new URLSearchParams()
    if (params.sourceKey) q.set("source_key", params.sourceKey)
    if (params.search) q.set("search", params.search)
    if (params.enabled !== undefined) q.set("enabled", String(params.enabled))
    if (params.lastRunStatus) q.set("last_run_status", params.lastRunStatus)
    q.set("limit", String(params.limit ?? 20))
    q.set("offset", String(params.offset ?? 0))
    return api.get<GenreListResult>(`${BASE}/genres?${q.toString()}`)
  },
  toggleGenre: (id: number, enabled: boolean) => api.patch<Genre>(`${BASE}/genres/${id}`, { enabled }),
  // Chạy nền phía BE — trả về NGAY Genre ở trạng thái "running" (202), chưa
  // có kết quả. Kết quả thật nằm ở Genre.last_run_* sau khi FE poll lại
  // listGenres() và thấy last_run_status chuyển done/error (mục 9.2).
  runGenreNow: (id: number) => api.post<Genre>(`${BASE}/genres/${id}/run-now`),
  cancelGenreRun: (id: number) => api.post<Genre>(`${BASE}/genres/${id}/cancel`),
  getGenreProgress: (id: number) =>
    api.get<GenreProgressResult>(`${BASE}/genres/${id}/progress`),

  listNovels: (params: NovelListParams = {}) => {
    const q = new URLSearchParams()
    if (params.status) q.set("status", params.status)
    if (params.sourceKey) q.set("source_key", params.sourceKey)
    if (params.search) q.set("search", params.search)
    if (params.isManual !== undefined) q.set("is_manual", String(params.isManual))
    if (params.genreId !== undefined) q.set("genre_id", String(params.genreId))
    q.set("limit", String(params.limit ?? 20))
    q.set("offset", String(params.offset ?? 0))
    return api.get<NovelListResult>(`${BASE}/novels?${q.toString()}`)
  },
  getNovel: (id: number) => api.get<Novel>(`${BASE}/novels/${id}`),
  listChapters: (novelId: number, params: ChapterListParams = {}) => {
    const q = new URLSearchParams()
    if (params.status) q.set("status", params.status)
    if (params.search) q.set("search", params.search)
    if (params.reviewed !== undefined) q.set("reviewed", String(params.reviewed))
    if (params.has_cleaned !== undefined) q.set("has_cleaned", String(params.has_cleaned))
    q.set("limit", String(params.limit ?? 20))
    q.set("offset", String(params.offset ?? 0))
    return api.get<ChapterListResult>(`${BASE}/novels/${novelId}/chapters?${q.toString()}`)
  },
  addNovel: (sourceKey: string, url: string) =>
    api.post<CrawlNovelResult>(`${BASE}/novels`, { source_key: sourceKey, url }),
  retryNovel: (id: number) => api.post<CrawlNovelResult>(`${BASE}/novels/${id}/retry`),
  retryErrorNovels: (params: {
    sourceKey: string
    genreId?: number
    isManual?: boolean
    limit?: number
  }) =>
    api.post<RetryErrorsResult>(`${BASE}/novels/retry-errors`, {
      source_key: params.sourceKey,
      genre_id: params.genreId,
      is_manual: params.isManual,
      limit: params.limit ?? 100,
    }),
  forceAcceptNovel: (id: number) => api.post<CrawlNovelResult>(`${BASE}/novels/${id}/force-accept`),
  smoothNovel: (id: number, chapterIds?: number[]) =>
    api.post<SmoothNovelResult>(`${BASE}/novels/${id}/smooth`, {
      chapter_ids: chapterIds && chapterIds.length > 0 ? chapterIds : null,
    }),
  sendToTranslate: (
    id: number,
    opts?: { require_cleaned?: boolean; start_job?: boolean },
  ) =>
    api.post<{
      novel_id: number
      lifecycle_status: string
      work_id: number
      variant_id: number
      job_id: number | null
      missing_cleaned: number
      unreviewed: number
      translate_path: string
    }>(`${BASE}/novels/${id}/send-to-translate`, {
      require_cleaned: opts?.require_cleaned ?? true,
      // false mặc định: chỉ handoff, để user chọn AI + mode ở modal "Bắt đầu dịch"
      // bên translate-service (tự mở khi Work chưa có job nào) thay vì tự chạy
      // job với default provider/model không ai chọn.
      start_job: opts?.start_job ?? false,
    }),
  getExportStatus: (id: number) => api.get<NovelExportStatus>(`${BASE}/novels/${id}/export-status`),
  exportNovelWorkbook: (id: number) =>
    api.download(`${BASE}/novels/${id}/export.xlsx`, `novel-${id}.xlsx`),
  exportNovelTxt: (id: number) => api.download(`${BASE}/novels/${id}/export.txt`, `novel-${id}.txt`),
  exportNovelEpub: (id: number) =>
    api.download(`${BASE}/novels/${id}/export.epub`, `novel-${id}.epub`),
  exportNovelBundle: (id: number) =>
    api.download(`${BASE}/novels/${id}/export.zip`, `novel-${id}.zip`),
  exportNovelsBatch: (novelIds: number[], format: string = "bundle") =>
    api.download(`${BASE}/novels/export-batch`, `export-batch.zip`, {
      method: "POST",
      body: { novel_ids: novelIds, format },
    }),
  reviewAllChapters: (id: number) =>
    api.post<ReviewAllResult>(`${BASE}/novels/${id}/review-all`),

  getSettings: () => api.get<SettingsValues>(`${BASE}/settings`),
  updateSettings: (values: Record<string, number | string | boolean>) =>
    api.patch<SettingsValues>(`${BASE}/settings`, { values }),

  getSiteSession: (sourceKey: string) =>
    api.get<SiteSession>(`${BASE}/sites/${encodeURIComponent(sourceKey)}/session`),
  saveSiteSession: (sourceKey: string, cookieHeader: string) =>
    api.put<SiteSession>(`${BASE}/sites/${encodeURIComponent(sourceKey)}/session`, {
      cookie_header: cookieHeader,
    }),
  probeSiteSession: (sourceKey: string) =>
    api.post<SiteSessionProbe>(`${BASE}/sites/${encodeURIComponent(sourceKey)}/session/probe`),

  dryRun: (sourceKey: string, url: string, mode: DryRunMode) =>
    api.post<DryRunResult>(`${BASE}/dry-run`, { source_key: sourceKey, url, mode }),

  getChapterContent: (chapterId: number) => api.get<ChapterContent>(`${BASE}/chapters/${chapterId}/content`),
  updateChapterContent: (chapterId: number, content: string) =>
    api.put<ChapterContent>(`${BASE}/chapters/${chapterId}/content`, { content }),
  discardChapterCleaned: (chapterId: number) =>
    api.delete<ChapterContent>(`${BASE}/chapters/${chapterId}/cleaned`),
  deleteChapter: (chapterId: number) =>
    api.delete<{ success: boolean; error?: string | null }>(`${BASE}/chapters/${chapterId}`),
  deleteNovel: (id: number) =>
    api.delete<{ success: boolean; error?: string | null }>(`${BASE}/novels/${id}`),
  // Crawl lại ĐÚNG 1 chương lỗi — khác retryNovel (cả truyện), mục 9.6.
  retryChapter: (chapterId: number) =>
    api.post<ChapterRetryResult>(`${BASE}/chapters/${chapterId}/retry`),
}
