/** Lỗi job/segment mang mã đầu dòng ("[rate_limited] …") — đổi sang câu dễ hiểu. */
import type { TranslateFn } from "@/i18n/types"

export const ERROR_CODES = [
  "rate_limited",
  "auth",
  "too_large",
  "truncated",
  "network",
  "refusal",
  "worker_crashed",
  "provider_error",
] as const

/** Cờ QA backend gắn cho segment (Segment.qa_flags). */
export const QA_FLAGS = [
  "refusal",
  "untranslated",
  "length_ratio",
  "repetition",
  "polish_failed",
  "leftover_original_name",
] as const

const CODES = ERROR_CODES.join("|")
/** Định dạng chuẩn "[code] message"; vẫn nhận kiểu cũ "code: message". */
const BRACKET_RE = new RegExp(`^\\s*\\[(${CODES})\\]\\s*([\\s\\S]*)$`)
const LEGACY_RE = new RegExp(`^\\s*(${CODES})\\s*:\\s*([\\s\\S]*)$`)

/** Tách mã lỗi (nếu có) khỏi chuỗi lỗi thô. */
export function parseErrorCode(raw: string | null | undefined): { code: string | null; detail: string } {
  if (!raw) return { code: null, detail: "" }
  const m = BRACKET_RE.exec(raw) ?? LEGACY_RE.exec(raw)
  if (!m) return { code: null, detail: raw }
  return { code: m[1], detail: m[2].trim() }
}

/** "[rate_limited] 429 Too Many…" → "Nhà cung cấp đang giới hạn tốc độ… (429 Too Many…)". */
export function friendlyError(raw: string | null | undefined, t: TranslateFn): string {
  if (!raw) return ""
  const { code, detail } = parseErrorCode(raw)
  if (!code) return raw
  const label = t(`translate.errorCode_${code}`)
  return detail ? `${label} (${detail})` : label
}

/** Nhãn cờ QA đã dịch; cờ lạ (backend thêm sau) hiện nguyên tên. */
export function qaFlagLabel(flag: string, t: TranslateFn): string {
  const key = `translate.qa_${flag}`
  const label = t(key)
  return label === key ? flag : label
}
