import { aiApi } from "@/features/ai/api"
import { ApiError, connectionError, responseError } from "../../api/client"
import { translate } from "@/i18n"
import { authFetch, saveBlob } from "../../api/authToken"
import type {
  AiProviderInput,
  Estimate,
  GlossaryTerm,
  GlossaryTermInput,
  Inbox,
  Job,
  ModelsInfo,
  NameExtractResult,
  NameItem,
  ProviderConfig,
  RenameBatch,
  RenameResult,
  Segment,
  SegmentDetail,
  SettingsValues,
  SkinMapRow,
  StyleProfile,
  UndoResult,
  Variant,
  Work,
  WorkList,
} from "./types"

const BASE = "/api/translate"

const envTranslateBase = import.meta.env.VITE_TRANSLATE_API_BASE_URL as string | undefined

/** Dev: dịch chạy port riêng; Docker/nginx: cùng origin (để trống). */
function translateRoot(): string {
  if (envTranslateBase !== undefined && envTranslateBase !== "") {
    return envTranslateBase.replace(/\/$/, "")
  }
  if (import.meta.env.DEV) {
    return "http://localhost:8010"
  }
  return ""
}

async function tRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const root = translateRoot()
  let res: Response
  try {
    res = await authFetch(`${root}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw connectionError("translate-service", root)
  }
  if (!res.ok) throw await responseError(res)
  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

export const translateApi = {
  listWorks: () => tRequest<WorkList>(`${BASE}/works`),
  getWork: (id: number) => tRequest<Work>(`${BASE}/works/${id}`),
  deleteWork: (id: number) => tRequest<void>(`${BASE}/works/${id}`, { method: "DELETE" }),
  importTxt: (body: {
    title: string
    author?: string
    lang_src: string
    lang_tgt?: string
    text: string
  }) =>
    tRequest<Work>(`${BASE}/works/import-txt`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listGlossary: (workId: number) =>
    tRequest<GlossaryTerm[]>(`${BASE}/works/${workId}/glossary`),
  addGlossary: (workId: number, body: GlossaryTermInput) =>
    tRequest<GlossaryTerm>(`${BASE}/works/${workId}/glossary`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** PUT thay cả term (backend bắt buộc source_term) — gửi đủ field hiện có. */
  updateGlossary: (workId: number, termId: number, body: GlossaryTermInput) =>
    tRequest<GlossaryTerm>(`${BASE}/works/${workId}/glossary/${termId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // Bảng duyệt tên (glossary mở rộng: kind/status + số lần xuất hiện)
  listNames: (workId: number) => tRequest<NameItem[]>(`${BASE}/works/${workId}/names`),
  extractNames: (workId: number, body: { provider_id?: number; sample_chapters?: number }) =>
    tRequest<NameExtractResult>(`${BASE}/works/${workId}/names/extract`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  approveNames: (workId: number, termIds: number[]) =>
    tRequest<NameItem[]>(`${BASE}/works/${workId}/names/approve`, {
      method: "POST",
      body: JSON.stringify({ term_ids: termIds }),
    }),
  applyNames: (
    workId: number,
    body: {
      changes: { term_id: number; new_target: string }[]
      variant_ids?: number[]
      dry_run: boolean
    },
  ) =>
    tRequest<RenameResult>(`${BASE}/works/${workId}/names/apply`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listRenameBatches: (workId: number) =>
    tRequest<RenameBatch[]>(`${BASE}/works/${workId}/names/batches`),
  undoRenameBatch: (workId: number, batchId: number) =>
    tRequest<UndoResult>(`${BASE}/works/${workId}/names/batches/${batchId}/undo`, { method: "POST" }),

  // Bảng "đổi vỏ" (skin map) của variant reskin
  listSkinMap: (variantId: number) => tRequest<SkinMapRow[]>(`${BASE}/variants/${variantId}/skin-map`),
  generateSkinMap: (variantId: number, body: { provider_id?: number; overwrite?: boolean }) =>
    tRequest<SkinMapRow[]>(`${BASE}/variants/${variantId}/skin-map/generate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  addSkinMapRow: (variantId: number, body: { original: string; replacement: string; kind?: string }) =>
    tRequest<SkinMapRow>(`${BASE}/variants/${variantId}/skin-map`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateSkinMapRow: (
    variantId: number,
    rowId: number,
    body: { replacement?: string; kind?: string; locked?: boolean },
  ) =>
    tRequest<SkinMapRow>(`${BASE}/variants/${variantId}/skin-map/${rowId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteSkinMapRow: (variantId: number, rowId: number) =>
    tRequest<void>(`${BASE}/variants/${variantId}/skin-map/${rowId}`, { method: "DELETE" }),
  applySkinMap: (
    variantId: number,
    body: { changes: { row_id: number; new_replacement: string }[]; dry_run: boolean },
  ) =>
    tRequest<RenameResult>(`${BASE}/variants/${variantId}/skin-map/apply`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteGlossary: (workId: number, termId: number) =>
    tRequest<void>(`${BASE}/works/${workId}/glossary/${termId}`, { method: "DELETE" }),

  createVariant: (
    workId: number,
    body: { mode: string; mode_params?: Record<string, unknown>; lang_tgt?: string },
  ) =>
    tRequest<Variant>(`${BASE}/works/${workId}/variants`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cloneVariant: (
    variantId: number,
    body?: { mode?: string; mode_params?: Record<string, unknown>; lang_tgt?: string },
  ) =>
    tRequest<Variant>(`${BASE}/variants/${variantId}/clone`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  listStyleProfiles: () => tRequest<StyleProfile[]>(`${BASE}/style-profiles`),

  estimate: (variantId: number) =>
    tRequest<Estimate>(`${BASE}/variants/${variantId}/estimate`),
  estimateWork: (workId: number, mode: string = "full", polish = false) =>
    tRequest<Estimate>(
      `${BASE}/works/${workId}/estimate?mode=${encodeURIComponent(mode)}&polish=${polish ? "true" : "false"}`,
    ),
  importEpub: async (body: { file: File; title: string; author: string; lang_src: string }) => {
    const fd = new FormData()
    fd.append("file", body.file)
    fd.append("title", body.title)
    fd.append("author", body.author)
    fd.append("lang_src", body.lang_src)
    fd.append("lang_tgt", "vi")
    const root = translateRoot()
    let res: Response
    try {
      res = await authFetch(`${root}${BASE}/works/import-epub`, { method: "POST", body: fd })
    } catch {
      throw connectionError("translate-service", root)
    }
    if (!res.ok) throw await responseError(res)
    return (await res.json()) as Work
  },
  listModels: () => tRequest<ModelsInfo>(`${BASE}/models`),
  startJob: (variantId: number, body?: ProviderConfig) =>
    tRequest<Job>(`${BASE}/variants/${variantId}/jobs`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  getJob: (jobId: number) => tRequest<Job>(`${BASE}/jobs/${jobId}`),
  resumeJob: (jobId: number, body?: ProviderConfig) =>
    tRequest<Job>(`${BASE}/jobs/${jobId}/resume`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  cancelJob: (jobId: number) =>
    tRequest<Job>(`${BASE}/jobs/${jobId}/cancel`, { method: "POST" }),
  pauseJob: (jobId: number) =>
    tRequest<Job>(`${BASE}/jobs/${jobId}/pause`, { method: "POST" }),
  deleteJob: (jobId: number) =>
    tRequest<void>(`${BASE}/jobs/${jobId}`, { method: "DELETE" }),
  patchJobProvider: (jobId: number, body: ProviderConfig) =>
    tRequest<Job>(`${BASE}/jobs/${jobId}/provider`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  patchJobModel: (jobId: number, model: string) =>
    tRequest<Job>(`${BASE}/jobs/${jobId}/model`, {
      method: "PATCH",
      body: JSON.stringify({ model }),
    }),
  /** Reset segment bị QA gắn cờ (lọc theo flag nếu có) rồi chạy tiếp job. */
  retranslateFlagged: (jobId: number, flag?: string) =>
    tRequest<Job>(
      `${BASE}/jobs/${jobId}/retranslate-flagged${flag ? `?flag=${encodeURIComponent(flag)}` : ""}`,
      { method: "POST" },
    ),
  listSegments: (jobId: number) =>
    tRequest<Segment[]>(`${BASE}/jobs/${jobId}/segments`),
  getSegment: (segmentId: number) =>
    tRequest<SegmentDetail>(`${BASE}/segments/${segmentId}`),
  putSegment: (segmentId: number, body: { output_text: string; reviewed?: boolean }) =>
    tRequest<SegmentDetail>(`${BASE}/segments/${segmentId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getSettings: () => tRequest<SettingsValues>(`${BASE}/settings`),
  updateSettings: (values: Record<string, unknown>) =>
    tRequest<SettingsValues>(`${BASE}/settings`, {
      method: "PUT",
      body: JSON.stringify({ values }),
    }),

  exportTxt: async (variantId: number) => {
    const root = translateRoot()
    const res = await authFetch(`${root}${BASE}/variants/${variantId}/export.txt`)
    if (!res.ok) {
      throw new ApiError(translate("app.exportFailed", { status: res.status }), res.status)
    }
    const blob = await res.blob()
    saveBlob(blob, `variant-${variantId}.txt`)
  },

  exportJson: async (variantId: number) => {
    const root = translateRoot()
    const res = await authFetch(`${root}${BASE}/variants/${variantId}/export.json`)
    if (!res.ok) {
      throw new ApiError(translate("app.exportFailed", { status: res.status }), res.status)
    }
    const blob = await res.blob()
    saveBlob(blob, `variant-${variantId}.json`)
  },

  exportEpub: async (variantId: number, bilingual = false) => {
    const root = translateRoot()
    const q = bilingual ? "?bilingual=true" : ""
    const res = await authFetch(`${root}${BASE}/variants/${variantId}/export.epub${q}`)
    if (!res.ok) {
      throw new ApiError(translate("app.exportFailed", { status: res.status }), res.status)
    }
    const blob = await res.blob()
    saveBlob(blob, bilingual ? `variant-${variantId}.bilingual.epub` : `variant-${variantId}.epub`)
  },

  listAiProviders: () => aiApi.listProviders(),
  createAiProvider: (body: AiProviderInput) => aiApi.createProvider(body),
  updateAiProvider: (id: number, body: Partial<AiProviderInput>) => aiApi.updateProvider(id, body),
  deleteAiProvider: (id: number) => aiApi.deleteProvider(id),
  addAiProviderKey: (id: number, api_key: string) => aiApi.addProviderKey(id, api_key),
  deleteAiProviderKey: (id: number, index: number) => aiApi.deleteProviderKey(id, index),

  getInbox: () => tRequest<Inbox>(`${BASE}/inbox`),
}
