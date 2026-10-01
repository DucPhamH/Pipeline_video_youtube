// Token dùng chung (FOLIO_API_TOKEN phía backend) — 1 store duy nhất cho mọi
// service. Backend không bật token thì header thừa bị bỏ qua, không hại gì.

const STORAGE_KEY = "folio.apiToken"
export const TOKEN_HEADER = "X-Folio-Token"

let memoryToken: string | null = null
const listeners = new Set<() => void>()

export function getApiToken(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved !== null) return saved
  } catch {
    /* private mode / storage bị chặn → dùng bản trong bộ nhớ */
  }
  return memoryToken ?? ""
}

export function setApiToken(token: string) {
  const next = token.trim()
  memoryToken = next || null
  try {
    if (next) localStorage.setItem(STORAGE_KEY, next)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
  listeners.forEach((fn) => fn())
}

export function clearApiToken() {
  setApiToken("")
}

/** Đăng ký nghe đổi token (useSyncExternalStore). */
export function subscribeApiToken(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** Gắn ?token= cho URL media/download dùng trực tiếp ở <audio src>/<a href>. */
export function withTokenQuery(url: string): string {
  const token = getApiToken()
  if (!token) return url
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`
}

// --- 401 → hỏi token ---------------------------------------------------------

type PromptHandler = () => Promise<boolean>
let promptHandler: PromptHandler | null = null
let pendingPrompt: Promise<boolean> | null = null

/** TokenPromptDialog đăng ký handler; trả true khi user lưu token mới. */
export function registerTokenPrompt(handler: PromptHandler | null) {
  promptHandler = handler
}

/** Gom nhiều 401 đồng thời vào 1 lần hỏi. */
function requestToken(): Promise<boolean> {
  if (!promptHandler) return Promise.resolve(false)
  if (!pendingPrompt) {
    pendingPrompt = promptHandler().finally(() => {
      pendingPrompt = null
    })
  }
  return pendingPrompt
}

function withTokenHeader(init: RequestInit | undefined, token: string): RequestInit {
  const headers = new Headers(init?.headers)
  if (token) headers.set(TOKEN_HEADER, token)
  return { ...init, headers }
}

/**
 * fetch kèm X-Folio-Token. Gặp 401 → mở hộp nhập token; user lưu thì thử lại 1 lần.
 * Không dùng cho body dạng stream (FormData/JSON string gửi lại được bình thường).
 */
export async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const sent = getApiToken()
  const res = await fetch(url, withTokenHeader(init, sent))
  if (res.status !== 401) return res
  // Token đã đổi trong lúc chờ (prompt khác vừa lưu) → thử lại luôn.
  const current = getApiToken()
  if (current && current !== sent) return fetch(url, withTokenHeader(init, current))
  const saved = await requestToken()
  if (!saved) return res
  return fetch(url, withTokenHeader(init, getApiToken()))
}

/** Tải blob về máy; thu hồi object URL sau khi trình duyệt kịp bắt đầu tải. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
