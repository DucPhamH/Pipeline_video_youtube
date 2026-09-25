import { ApiError } from "../../api/client"
import type {
  AiProvider,
  AiProviderInput,
  Estimate,
  GlossaryTerm,
  Inbox,
  Job,
  ModelsInfo,
  ProviderConfig,
  Segment,
  SegmentDetail,
  SettingsValues,
  StyleProfile,
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
    res = await fetch(`${root}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw new ApiError(
      `Không kết nối được translate-service (${root || "same-origin"})`,
      0,
    )
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const message = body?.detail ?? body?.error ?? `Lỗi HTTP ${res.status}`
    throw new ApiError(typeof message === "string" ? message : JSON.stringify(message), res.status)
  }
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
  addGlossary: (
    workId: number,
    body: { source_term: string; target_term: string; protected?: boolean; notes?: string },
  ) =>
    tRequest<GlossaryTerm>(`${BASE}/works/${workId}/glossary`, {
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
  estimateWork: (workId: number, mode: string = "full") =>
    tRequest<Estimate>(`${BASE}/works/${workId}/estimate?mode=${encodeURIComponent(mode)}`),
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
    const res = await fetch(`${root}${BASE}/variants/${variantId}/export.txt`)
    if (!res.ok) {
      throw new ApiError(`Export failed ${res.status}`, res.status)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `variant-${variantId}.txt`
    a.click()
    URL.revokeObjectURL(url)
  },

  exportJson: async (variantId: number) => {
    const root = translateRoot()
    const res = await fetch(`${root}${BASE}/variants/${variantId}/export.json`)
    if (!res.ok) {
      throw new ApiError(`Export failed ${res.status}`, res.status)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `variant-${variantId}.json`
    a.click()
    URL.revokeObjectURL(url)
  },

  listAiProviders: () => tRequest<AiProvider[]>(`${BASE}/ai-providers`),
  createAiProvider: (body: AiProviderInput) =>
    tRequest<AiProvider>(`${BASE}/ai-providers`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateAiProvider: (id: number, body: Partial<AiProviderInput>) =>
    tRequest<AiProvider>(`${BASE}/ai-providers/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteAiProvider: (id: number) =>
    tRequest<void>(`${BASE}/ai-providers/${id}`, { method: "DELETE" }),
  addAiProviderKey: (id: number, api_key: string) =>
    tRequest<AiProvider>(`${BASE}/ai-providers/${id}/keys`, {
      method: "POST",
      body: JSON.stringify({ api_key }),
    }),
  deleteAiProviderKey: (id: number, index: number) =>
    tRequest<AiProvider>(`${BASE}/ai-providers/${id}/keys/${index}`, { method: "DELETE" }),

  getInbox: () => tRequest<Inbox>(`${BASE}/inbox`),
}
