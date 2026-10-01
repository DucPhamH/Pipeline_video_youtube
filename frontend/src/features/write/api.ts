import { connectionError, responseError } from "@/api/client"
import { authFetch } from "@/api/authToken"

const BASE = "/api/write"
const envWriteBase = import.meta.env.VITE_WRITE_API_BASE_URL as string | undefined

function writeRoot(): string {
  if (envWriteBase !== undefined && envWriteBase !== "") {
    return envWriteBase.replace(/\/$/, "")
  }
  if (import.meta.env.DEV) {
    return "http://localhost:8012"
  }
  return ""
}

export type StoryCharacter = { name: string; role: string }

export type StoryChapter = { index: number; title: string; beat: string; text: string }

export type Story = {
  id: number
  title: string
  premise: string
  ending: string
  chapter_count: number
  provider_id: number | null
  status: string
  write_error: string
  characters: StoryCharacter[]
  chapters: StoryChapter[]
}

export type StoryListItem = {
  id: number
  title: string
  chapter_count: number
  filled_count: number
  status: string
}

export type StoryInput = {
  title: string
  premise: string
  ending: string
  chapter_count: number
  provider_id: number
  characters: StoryCharacter[]
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const root = writeRoot()
  let res: Response
  try {
    res = await authFetch(`${root}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw connectionError("write-service", root)
  }
  if (!res.ok) throw await responseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const writeApi = {
  list: () => request<{ items: StoryListItem[] }>(`${BASE}/stories`),
  get: (id: number) => request<Story>(`${BASE}/stories/${id}`),
  create: (body: StoryInput) =>
    request<Story>(`${BASE}/stories`, { method: "POST", body: JSON.stringify(body) }),
  patch: (id: number, body: Partial<StoryInput>) =>
    request<Story>(`${BASE}/stories/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: number) => request<void>(`${BASE}/stories/${id}`, { method: "DELETE" }),
  patchChapter: (id: number, index: number, body: Partial<StoryChapter>) =>
    request<Story>(`${BASE}/stories/${id}/chapters/${index}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  outline: (id: number, replace: boolean) =>
    request<Story>(`${BASE}/stories/${id}/outline?replace=${replace ? "true" : "false"}`, { method: "POST" }),
  writeChapter: (id: number, index: number, force: boolean) =>
    request<Story>(`${BASE}/stories/${id}/chapters/${index}/write`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
  streamChapter: async (id: number, index: number, force: boolean, onDelta: (text: string) => void) => {
    const res = await authFetch(`${writeRoot()}${BASE}/stories/${id}/chapters/${index}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    })
    if (!res.ok) throw await responseError(res)
    if (!res.body) throw new Error("stream")
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ""
    let full = ""
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const chunks = buf.split("\n\n")
      buf = chunks.pop() ?? ""
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((item) => item.startsWith("data:"))
        if (!line) continue
        const payload = JSON.parse(line.slice(line.indexOf(":") + 1)) as {
          delta?: string
          error?: string
        }
        if (payload.error) throw new Error(payload.error)
        if (payload.delta) {
          full += payload.delta
          onDelta(full)
        }
      }
    }
  },
  writeAll: (id: number) => request<Story>(`${BASE}/stories/${id}/write`, { method: "POST" }),
  stop: (id: number) => request<Story>(`${BASE}/stories/${id}/stop`, { method: "POST" }),
}
