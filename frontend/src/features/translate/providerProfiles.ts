/**
 * @deprecated Phần "profiles" (localStorage, 1 AI active tại 1 thời điểm) đã được
 * thay bằng registry AI thật trên backend (`/api/translate/ai-providers`, xem
 * `api.ts` + `AiProvidersPanel.tsx`). Giữ file này lại để `migrateLegacyProfilesOnce()`
 * import 1 lần các profile cũ (đã có key) sang registry mới; đừng dùng
 * `saveProviderProfile`/`getActiveProfile`/... cho tính năng mới.
 *
 * `AI_CATALOG` (metadata: base_url/model gợi ý theo từng "kind") vẫn còn dùng —
 * đây là danh mục tham khảo khi tạo AI provider mới, không liên quan tới việc
 * lưu 1 "active profile".
 */
import type { ProviderProfile } from "./types"

const STORE_KEY = "translate.providerProfiles.v1"

export type AiCatalogEntry = {
  id: string
  label: string
  blurb: string
  provider: "openai" | "mock"
  base_url: string
  default_model: string
  model_suggestions: string[]
  docs_url?: string
  /** true = URL/model cố định gợi ý; user vẫn sửa được */
  popular: boolean
}

/** Nhà AI phổ biến — OpenAI-compatible (dịch dùng /chat/completions). */
export const AI_CATALOG: AiCatalogEntry[] = [
  {
    id: "openai",
    label: "OpenAI (GPT)",
    blurb: "GPT-4o / o-series — chất lượng cao",
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o",
    model_suggestions: [
      "gpt-4o",
      "gpt-4o-mini",
      "gpt-4.1",
      "gpt-4.1-mini",
      "gpt-4.1-nano",
      "gpt-4-turbo",
      "gpt-3.5-turbo",
      "o1",
      "o1-mini",
      "o3-mini",
      "o4-mini",
      "chatgpt-4o-latest",
    ],
    docs_url: "https://platform.openai.com/api-keys",
    popular: true,
  },
  {
    id: "claude",
    label: "Anthropic (Claude)",
    blurb: "Claude — endpoint OpenAI-compatible",
    provider: "openai",
    base_url: "https://api.anthropic.com/v1",
    default_model: "claude-sonnet-4-0",
    model_suggestions: [
      "claude-opus-4-0",
      "claude-sonnet-4-0",
      "claude-3-7-sonnet-latest",
      "claude-3-5-sonnet-latest",
      "claude-3-5-sonnet-20241022",
      "claude-3-5-haiku-latest",
      "claude-3-5-haiku-20241022",
      "claude-3-opus-latest",
      "claude-3-haiku-20240307",
    ],
    docs_url: "https://console.anthropic.com/settings/keys",
    popular: true,
  },
  {
    id: "gemini",
    label: "Google Gemini",
    blurb: "Gemini Flash/Pro — endpoint OpenAI-compatible",
    provider: "openai",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    // "-latest" là alias ổn định Google tự trỏ sang bản mới nhất — ưu tiên làm
    // mặc định để đỡ bị lỗi thời khi Google ngừng hỗ trợ bản cũ (đã gặp thật:
    // gemini-2.0-flash/1.5-* bị retire, xem CHANGELOG).
    default_model: "gemini-flash-latest",
    model_suggestions: [
      "gemini-flash-latest",
      "gemini-pro-latest",
      "gemini-2.5-flash",
      "gemini-2.5-pro",
      "gemini-2.5-flash-lite",
      "gemini-3.6-flash",
    ],
    docs_url: "https://aistudio.google.com/apikey",
    popular: true,
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    blurb: "Rẻ, mạnh cho dịch văn dài",
    provider: "openai",
    base_url: "https://api.deepseek.com/v1",
    default_model: "deepseek-chat",
    model_suggestions: [
      "deepseek-chat",
      "deepseek-reasoner",
      "deepseek-coder",
    ],
    docs_url: "https://platform.deepseek.com/api_keys",
    popular: true,
  },
  {
    id: "groq",
    label: "Groq",
    blurb:
      "Rất nhanh — free tier hữu ích. Danh sách model Groq đổi khá thường xuyên " +
      "(model cũ bị deprecate) — nếu model gợi ý báo 404 model_not_found, tự kiểm " +
      "tra danh sách hiện có tại console.groq.com/docs/models rồi gõ tay vào ô 'Model khác'.",
    provider: "openai",
    base_url: "https://api.groq.com/openai/v1",
    default_model: "llama-3.1-8b-instant",
    model_suggestions: [
      "llama-3.1-8b-instant",
      "gemma2-9b-it",
      "llama-3.3-70b-versatile",
      "llama-3.1-70b-versatile",
      "qwen/qwen3.8-27b",
      "llama3-70b-8192",
      "llama3-8b-8192",
      "mixtral-8x7b-32768",
      "openai/gpt-oss-120b",
      "openai/gpt-oss-20b",
      "deepseek-r1-distill-llama-70b",
      "meta-llama/llama-4-scout-17b-16e-instruct",
      "meta-llama/llama-4-maverick-17b-128e-instruct",
    ],
    docs_url: "https://console.groq.com/keys",
    popular: true,
  },
  {
    id: "mistral",
    label: "Mistral",
    blurb: "Mistral Large / Small / Codestral",
    provider: "openai",
    base_url: "https://api.mistral.ai/v1",
    default_model: "mistral-large-latest",
    model_suggestions: [
      "mistral-large-latest",
      "mistral-medium-latest",
      "mistral-small-latest",
      "open-mistral-nemo",
      "open-mixtral-8x22b",
      "open-mixtral-8x7b",
      "codestral-latest",
      "ministral-8b-latest",
      "ministral-3b-latest",
      "pixtral-large-latest",
    ],
    docs_url: "https://console.mistral.ai/api-keys",
    popular: true,
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    blurb: "Một key → Claude / GPT / Gemini /…",
    provider: "openai",
    base_url: "https://openrouter.ai/api/v1",
    default_model: "anthropic/claude-sonnet-4",
    model_suggestions: [
      "anthropic/claude-opus-4",
      "anthropic/claude-sonnet-4",
      "anthropic/claude-3.7-sonnet",
      "anthropic/claude-3.5-sonnet",
      "openai/gpt-4o",
      "openai/gpt-4o-mini",
      "openai/o4-mini",
      "google/gemini-2.5-pro-preview",
      "google/gemini-2.5-flash-preview",
      "google/gemini-2.0-flash-001",
      "deepseek/deepseek-chat",
      "deepseek/deepseek-r1",
      "meta-llama/llama-3.3-70b-instruct",
      "qwen/qwen-2.5-72b-instruct",
      "mistralai/mistral-large",
      "x-ai/grok-3-beta",
    ],
    docs_url: "https://openrouter.ai/keys",
    popular: true,
  },
  {
    id: "xai",
    label: "xAI (Grok)",
    blurb: "Grok — OpenAI-compatible",
    provider: "openai",
    base_url: "https://api.x.ai/v1",
    default_model: "grok-2-latest",
    model_suggestions: [
      "grok-3",
      "grok-3-mini",
      "grok-3-fast",
      "grok-3-mini-fast",
      "grok-2-latest",
      "grok-2",
      "grok-2-mini",
      "grok-beta",
    ],
    docs_url: "https://console.x.ai",
    popular: true,
  },
  {
    id: "qwen",
    label: "Qwen (DashScope)",
    blurb: "Alibaba Qwen — compatible-mode",
    provider: "openai",
    base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    default_model: "qwen-plus",
    model_suggestions: [
      "qwen-max",
      "qwen-max-latest",
      "qwen-plus",
      "qwen-plus-latest",
      "qwen-turbo",
      "qwen-turbo-latest",
      "qwen-long",
      "qwen2.5-72b-instruct",
      "qwen2.5-32b-instruct",
      "qwen2.5-14b-instruct",
      "qwen2.5-7b-instruct",
      "qwq-32b",
      "qwen-mt-turbo",
      "qwen-mt-plus",
    ],
    docs_url: "https://dashscope.console.aliyun.com",
    popular: true,
  },
  {
    id: "local",
    label: "AI local (Ollama / LM Studio)",
    blurb:
      "Chạy trên máy — endpoint OpenAI-compatible, thường không cần API key. " +
      "URL mặc định dùng được ngay nếu chạy bằng docker-compose (repo này); " +
      "nếu chạy translate-service trực tiếp (không Docker) thì đổi lại thành " +
      "http://localhost:11434/v1 (Ollama) hoặc http://localhost:1234/v1 (LM Studio).",
    provider: "openai",
    base_url: "http://host.docker.internal:11434/v1",
    default_model: "qwen2.5",
    model_suggestions: ["qwen2.5", "llama3.1", "deepseek-r1", "mistral", "gemma2"],
    popular: true,
  },
  {
    id: "mock",
    label: "Mock (dev)",
    blurb: "Không gọi API — test UI / pipeline",
    provider: "mock",
    base_url: "",
    default_model: "mock",
    model_suggestions: ["mock"],
    popular: true,
  },
]

/** kind không cần api_key theo mặc định (user vẫn có thể bật lại nếu cần). */
export const KINDS_NO_KEY_REQUIRED = new Set(["local", "mock"])

type Store = {
  profiles: ProviderProfile[]
  activeId: string | null
}

function emptyStore(): Store {
  return { profiles: [], activeId: null }
}

function readStore(): Store {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (!raw) return emptyStore()
    const parsed = JSON.parse(raw) as Store
    if (!Array.isArray(parsed.profiles)) return emptyStore()
    return {
      profiles: parsed.profiles,
      activeId: parsed.activeId ?? parsed.profiles[0]?.id ?? null,
    }
  } catch {
    return emptyStore()
  }
}

function writeStore(store: Store) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store))
  } catch {
    /* ignore quota */
  }
}

function catalogToProfile(entry: AiCatalogEntry, existing?: ProviderProfile): ProviderProfile {
  return {
    id: entry.id,
    label: entry.label,
    provider: entry.provider,
    model: existing?.model || entry.default_model,
    base_url: existing?.base_url || entry.base_url,
    api_key: existing?.api_key || "",
  }
}

/** Đảm bảo mọi AI trong catalog có profile (giữ key/model user đã lưu). */
export function ensureCatalogProfiles(): ProviderProfile[] {
  const s = readStore()
  const byId = new Map(s.profiles.map((p) => [p.id, p]))
  const merged: ProviderProfile[] = []
  for (const entry of AI_CATALOG) {
    merged.push(catalogToProfile(entry, byId.get(entry.id)))
    byId.delete(entry.id)
  }
  // Giữ custom profiles user tạo thêm
  for (const extra of byId.values()) merged.push(extra)
  const activeId =
    (s.activeId && merged.some((p) => p.id === s.activeId) ? s.activeId : null) ??
    merged.find((p) => p.id === "groq")?.id ??
    merged[0]?.id ??
    null
  writeStore({ profiles: merged, activeId })
  return merged
}

export function listProviderProfiles(): ProviderProfile[] {
  return ensureCatalogProfiles()
}

export function getActiveProfile(): ProviderProfile | null {
  const s = readStore()
  const profiles = ensureCatalogProfiles()
  return profiles.find((p) => p.id === s.activeId) ?? profiles[0] ?? null
}

export function saveProviderProfile(profile: ProviderProfile, makeActive = true) {
  ensureCatalogProfiles()
  const s = readStore()
  const idx = s.profiles.findIndex((p) => p.id === profile.id)
  if (idx >= 0) s.profiles[idx] = profile
  else s.profiles.push(profile)
  if (makeActive) s.activeId = profile.id
  writeStore(s)
}

export function saveAllProviderProfiles(profiles: ProviderProfile[], activeId?: string | null) {
  const s = readStore()
  writeStore({
    profiles,
    activeId: activeId !== undefined ? activeId : s.activeId,
  })
}

export function setActiveProfileId(id: string) {
  const s = readStore()
  if (s.profiles.some((p) => p.id === id) || AI_CATALOG.some((c) => c.id === id)) {
    ensureCatalogProfiles()
    const next = readStore()
    next.activeId = id
    writeStore(next)
  }
}

export function deleteProviderProfile(id: string) {
  if (AI_CATALOG.some((c) => c.id === id)) {
    // Catalog entry: chỉ xóa key, reset model/url về default
    const entry = AI_CATALOG.find((c) => c.id === id)!
    saveProviderProfile(catalogToProfile(entry), false)
    return
  }
  const s = readStore()
  s.profiles = s.profiles.filter((p) => p.id !== id)
  if (s.activeId === id) s.activeId = s.profiles[0]?.id ?? null
  writeStore(s)
}

export function newProfileId() {
  return `p_${Date.now().toString(36)}`
}

const MIGRATED_FLAG = "translate.providerProfiles.migratedToRegistry.v1"

/**
 * One-shot: đưa mọi profile cũ (localStorage) đã có api_key vào registry
 * backend mới, rồi đánh dấu đã migrate để không chạy lại. Gọi ở
 * `TranslateSettingsPage` khi mount — an toàn gọi nhiều lần (no-op sau lần đầu).
 */
export async function migrateLegacyProfilesOnce(
  createAiProvider: (body: {
    label: string
    kind: string
    base_url?: string
    model?: string
    api_key?: string
    requires_api_key?: boolean
  }) => Promise<unknown>,
): Promise<number> {
  try {
    if (localStorage.getItem(MIGRATED_FLAG)) return 0
  } catch {
    return 0
  }
  const s = readStore()
  const withKeys = s.profiles.filter((p) => p.provider !== "mock" && p.api_key.trim())
  let migrated = 0
  for (const p of withKeys) {
    try {
      await createAiProvider({
        label: p.label || p.id,
        kind: p.id,
        base_url: p.base_url,
        model: p.model,
        api_key: p.api_key,
        requires_api_key: true,
      })
      migrated += 1
    } catch {
      /* bỏ qua profile lỗi, vẫn đánh dấu đã chạy để không lặp lại */
    }
  }
  try {
    localStorage.setItem(MIGRATED_FLAG, "1")
  } catch {
    /* ignore quota */
  }
  return migrated
}

export function getCatalogEntry(id: string): AiCatalogEntry | undefined {
  return AI_CATALOG.find((c) => c.id === id)
}

/** @deprecated — dùng ensureCatalogProfiles */
export function seedDefaultProfiles(_defaults?: {
  provider: string
  model: string
  base_url: string
}): void {
  ensureCatalogProfiles()
}
