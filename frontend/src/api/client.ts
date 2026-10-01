// Fetch wrapper mỏng — cache/poll/abort do TanStack Query lo ở tầng page.
// Base URL đọc từ biến môi trường Vite, xem .env.example.

import { translate } from "@/i18n"
import { authFetch, saveBlob } from "./authToken"

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

/** Lỗi không tới được service (fetch reject) — message theo locale hiện tại. */
export function connectionError(service: string, root: string): ApiError {
  return new ApiError(
    translate("app.connectionError", { service, url: root || "same-origin" }),
    0,
  )
}

/** Dựng ApiError từ response !ok: ưu tiên detail/error của backend, fallback "HTTP {status}". */
export async function responseError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null)
  const message = body?.detail ?? body?.error ?? translate("app.httpError", { status: res.status })
  return new ApiError(typeof message === "string" ? message : JSON.stringify(message), res.status)
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await authFetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw connectionError("backend", BASE_URL)
  }

  if (!res.ok) throw await responseError(res)

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
      res = await authFetch(`${BASE_URL}${path}`, {
        method,
        headers: options?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
      })
    } catch {
      throw connectionError("backend", BASE_URL)
    }
    if (!res.ok) throw await responseError(res)
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
    saveBlob(blob, filename)
  },
}
