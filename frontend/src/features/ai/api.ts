import { connectionError, responseError } from "@/api/client"
import { authFetch } from "@/api/authToken"
import type { AiProvider, AiProviderInput } from "@/features/translate/types"

const BASE = "/api/ai"
const envAiBase = import.meta.env.VITE_AI_API_BASE_URL as string | undefined

function aiRoot(): string {
  if (envAiBase !== undefined && envAiBase !== "") {
    return envAiBase.replace(/\/$/, "")
  }
  if (import.meta.env.DEV) {
    return "http://localhost:8013"
  }
  return ""
}

async function aiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const root = aiRoot()
  let res: Response
  try {
    res = await authFetch(`${root}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw connectionError("ai-service", root)
  }
  if (!res.ok) throw await responseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export type UsageRow = {
  key: string
  label: string
  calls: number
  prompt_tokens: number
  completion_tokens: number
}

export type AiUsage = {
  days: number
  total: UsageRow
  by_day: UsageRow[]
  by_provider: UsageRow[]
  by_caller: UsageRow[]
}

export const aiApi = {
  usage: (days: number) => aiRequest<AiUsage>(`${BASE}/usage?days=${days}`),
  listProviders: () => aiRequest<AiProvider[]>(`${BASE}/providers`),
  createProvider: (body: AiProviderInput) =>
    aiRequest<AiProvider>(`${BASE}/providers`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateProvider: (id: number, body: Partial<AiProviderInput>) =>
    aiRequest<AiProvider>(`${BASE}/providers/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteProvider: (id: number) =>
    aiRequest<void>(`${BASE}/providers/${id}`, { method: "DELETE" }),
  addProviderKey: (id: number, api_key: string) =>
    aiRequest<AiProvider>(`${BASE}/providers/${id}/keys`, {
      method: "POST",
      body: JSON.stringify({ api_key }),
    }),
  deleteProviderKey: (id: number, index: number) =>
    aiRequest<AiProvider>(`${BASE}/providers/${id}/keys/${index}`, { method: "DELETE" }),
}
