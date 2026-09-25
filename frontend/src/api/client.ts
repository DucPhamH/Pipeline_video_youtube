// Fetch wrapper mỏng — cache/poll/abort do TanStack Query lo ở tầng page.
// Base URL đọc từ biến môi trường Vite, xem .env.example.

// Dev: trỏ API local. Docker image FE: build với VITE_API_BASE_URL="" (relative).
const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined
const BASE_URL =
  envBase === undefined || envBase === ""
    ? import.meta.env.DEV
      ? "http://localhost:8090"
      : ""
    : envBase

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw new ApiError(
      `Không kết nối được tới backend (${BASE_URL}) — backend có đang chạy không?`,
      0,
    )
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const message = body?.detail ?? body?.error ?? `Lỗi HTTP ${res.status}`
    throw new ApiError(typeof message === "string" ? message : JSON.stringify(message), res.status)
  }

  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "POST", body: data !== undefined ? JSON.stringify(data) : undefined }),
  patch: <T>(path: string, data: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(data) }),
  put: <T>(path: string, data: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(data) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  /** Tải file nhị phân (xlsx…) — không parse JSON. */
  download: async (
    path: string,
    fallbackName: string,
    options?: { method?: string; body?: unknown },
  ) => {
    let res: Response
    try {
      const method = options?.method ?? "GET"
      res = await fetch(`${BASE_URL}${path}`, {
        method,
        headers: options?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
      })
    } catch {
      throw new ApiError(
        `Không kết nối được tới backend (${BASE_URL}) — backend có đang chạy không?`,
        0,
      )
    }
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      const message = body?.detail ?? body?.error ?? `Lỗi HTTP ${res.status}`
      throw new ApiError(typeof message === "string" ? message : JSON.stringify(message), res.status)
    }
    const blob = await res.blob()
    const cd = res.headers.get("Content-Disposition")
    let filename = fallbackName
    const starred = cd?.match(/filename\*=UTF-8''([^;]+)/i)
    if (starred?.[1]) {
      try {
        filename = decodeURIComponent(starred[1])
      } catch {
        filename = starred[1]
      }
    } else {
      const m = cd?.match(/filename="?([^";]+)"?/i)
      if (m?.[1]) filename = m[1]
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}
