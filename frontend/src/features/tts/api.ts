import { connectionError, responseError } from "../../api/client"
import { authFetch, saveBlob, withTokenQuery } from "../../api/authToken"

const BASE = "/api/tts"

const envTtsBase = import.meta.env.VITE_TTS_API_BASE_URL as string | undefined

export function ttsRoot(): string {
  if (envTtsBase !== undefined && envTtsBase !== "") {
    return envTtsBase.replace(/\/$/, "")
  }
  if (import.meta.env.DEV) {
    return "http://localhost:8011"
  }
  return ""
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const root = ttsRoot()
  let res: Response
  try {
    res = await authFetch(`${root}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw connectionError("tts-service", root)
  }
  if (!res.ok) throw await responseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export type TtsVoice = {
  id: string
  label: string
  locale: string
  gender: string
  styles: string[]
}

export type TtsPreset = {
  id: string
  voice: string
  dialogue_voice: string
  rate: string
  pitch: string
  volume: string
  style: string
}

export type TtsChapter = { index: number; title: string }

export type TtsJob = {
  id: number
  reading_id: number
  status: string
  engine: string
  voice: string
  dialogue_voice: string
  rate: string
  pitch: string
  volume: string
  style: string
  error: string | null
  done_segments: number
  total_segments: number
  failed_segments: number
  skipped_segments?: number
  use_cast?: boolean
}

/** Hàng của GET /api/tts/jobs/active (job queued/running). */
export type TtsActiveJob = {
  job_id: number
  reading_id: number
  work_id: number
  work_title: string
  status: string
  done_segments: number
  total_segments: number
  skipped_segments?: number
}

export type TtsReading = {
  id: number
  work_id: number
  engine: string
  voice: string
  dialogue_voice: string
  rate: string
  pitch: string
  volume: string
  style: string
  status: string
  latest_job: TtsJob | null
}

export type TtsCastMember = {
  id: number
  name: string
  gender: string
  voice: string
}

export type TtsCastDraft = {
  name: string
  gender: string
  voice: string
}

export type TtsWork = {
  id: number
  title: string
  author: string
  lang: string
  source_type: string
  external_id: string | null
  chapters: TtsChapter[]
  readings: TtsReading[]
  cast: TtsCastMember[]
  created: boolean
}

export type TtsWorkListItem = {
  id: number
  title: string
  author: string
  lang: string
  source_type: string
  chapter_count: number
  /** Job mới nhất của reading mới nhất — backend cũ không trả. */
  latest_status?: string | null
  latest_done?: number
  latest_total?: number
}

export type TtsSegment = {
  id: number
  job_id: number
  chapter_index: number
  title: string
  status: string
  error: string | null
  has_audio: boolean
}

async function download(path: string, filename: string) {
  const root = ttsRoot()
  const res = await authFetch(`${root}${path}`)
  if (!res.ok) throw await responseError(res)
  const blob = await res.blob()
  saveBlob(blob, filename)
}

export const ttsApi = {
  listWorks: () => request<{ items: TtsWorkListItem[] }>(`${BASE}/works`),
  getWork: (id: number) => request<TtsWork>(`${BASE}/works/${id}`),
  importTxt: (body: { title: string; author: string; lang: string; text: string }) =>
    request<TtsWork>(`${BASE}/works/import-txt`, { method: "POST", body: JSON.stringify(body) }),
  importEpub: async (file: File, lang: string) => {
    const root = ttsRoot()
    const form = new FormData()
    form.set("file", file)
    form.set("lang", lang)
    const res = await authFetch(`${root}${BASE}/works/import-epub`, { method: "POST", body: form })
    if (!res.ok) throw await responseError(res)
    return (await res.json()) as TtsWork
  },
  fromTranslate: (body: {
    title: string
    author: string
    lang: string
    external_id: string
    chapters: { index: number; title: string; text: string }[]
  }) => request<TtsWork>(`${BASE}/works/from-translate`, { method: "POST", body: JSON.stringify(body) }),
  engines: () => request<{ edge: boolean; mock: boolean; vieneu: boolean; vieneu_gpu: boolean }>(`${BASE}/engines`),
  saveCast: (workId: number, members: TtsCastDraft[]) =>
    request<TtsWork>(`${BASE}/works/${workId}/cast`, {
      method: "PUT",
      body: JSON.stringify({ members }),
    }),
  detectCast: (workId: number, providerId: number) =>
    request<TtsWork>(`${BASE}/works/${workId}/cast/detect`, {
      method: "POST",
      body: JSON.stringify({ provider_id: providerId }),
    }),
  cloneVoice: async (file: File, name: string) => {
    const root = ttsRoot()
    const form = new FormData()
    form.set("file", file)
    form.set("name", name)
    const res = await authFetch(`${root}${BASE}/voices/clone`, { method: "POST", body: form })
    if (!res.ok) throw await responseError(res)
    return (await res.json()) as { id: string; label: string }
  },
  health: () => request<{ status: string; ffmpeg?: boolean }>(`${BASE}/health`),
  voices: (lang: string, engine: string) =>
    request<{ sample: string; voices: TtsVoice[] }>(
      `${BASE}/voices?lang=${encodeURIComponent(lang)}&engine=${encodeURIComponent(engine)}`,
    ),
  presets: (lang: string) => request<TtsPreset[]>(`${BASE}/presets?lang=${encodeURIComponent(lang)}`),
  preview: async (body: {
    engine: string
    voice: string
    lang: string
    rate: string
    pitch: string
    volume: string
    style: string
    device: string
  }) => {
    const root = ttsRoot()
    const res = await authFetch(`${root}${BASE}/voices/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw await responseError(res)
    const blob = await res.blob()
    return URL.createObjectURL(blob)
  },
  startReading: (
    workId: number,
    body: {
      engine: string
      voice: string
      dialogue_voice: string
      rate: string
      pitch: string
      volume: string
      style: string
      preset_id: string
      male_voice: string
      female_voice: string
      use_cast: boolean
      provider_id: number | null
      device: string
    },
  ) => request<TtsWork>(`${BASE}/works/${workId}/readings`, { method: "POST", body: JSON.stringify(body) }),
  activeJobs: () => request<TtsActiveJob[]>(`${BASE}/jobs/active`),
  segments: (jobId: number) => request<TtsSegment[]>(`${BASE}/jobs/${jobId}/segments`),
  resume: (jobId: number) => request<TtsJob>(`${BASE}/jobs/${jobId}/resume`, { method: "POST" }),
  cancel: (jobId: number) => request<TtsJob>(`${BASE}/jobs/${jobId}/cancel`, { method: "POST" }),
  audioUrl: (segmentId: number) => withTokenQuery(`${ttsRoot()}${BASE}/segments/${segmentId}/audio`),
  exportZip: (readingId: number) => download(`${BASE}/readings/${readingId}/export.zip`, `reading-${readingId}.zip`),
  exportM4b: (readingId: number) => download(`${BASE}/readings/${readingId}/export.m4b`, `reading-${readingId}.m4b`),
}
