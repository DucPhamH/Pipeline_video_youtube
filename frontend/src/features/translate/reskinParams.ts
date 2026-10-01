/** Params của mode "reskin" (giữ cốt, đổi vỏ): hằng số + validate + làm sạch. */
import type { TranslateFn } from "@/i18n/types"

export const RESKIN_SETTINGS = [
  "modern_urban",
  "vn_historical",
  "xianxia",
  "western_fantasy",
  "scifi",
  "school",
  "custom",
] as const
export const RESKIN_INTENSITIES = ["light", "medium", "heavy"] as const
export const RESKIN_CUSTOM_MAX = 500
export const RESKIN_NOTES_MAX = 1000

/** "A, B\nC" → ["A","B","C"] (bỏ trùng, bỏ rỗng). */
export function parseNameList(raw: string): string[] {
  const out: string[] = []
  for (const part of raw.split(/[,\n，、]/)) {
    const v = part.trim()
    if (v && !out.includes(v)) out.push(v)
  }
  return out
}

/** Lỗi params chặn submit (null = hợp lệ). */
export function modeParamsError(mode: string, params: Record<string, unknown>, t: TranslateFn): string | null {
  if (mode !== "reskin") return null
  const custom = String(params.custom_setting ?? "").trim()
  if (params.setting === "custom" && !custom) return t("translate.reskinCustomRequired")
  if (custom.length > RESKIN_CUSTOM_MAX) return t("translate.reskinTooLong", { max: RESKIN_CUSTOM_MAX })
  if (String(params.notes ?? "").length > RESKIN_NOTES_MAX) return t("translate.reskinTooLong", { max: RESKIN_NOTES_MAX })
  return null
}

/** Bỏ field thừa trước khi gửi (custom_setting chỉ khi setting=custom). */
export function cleanModeParams(mode: string, params: Record<string, unknown>): Record<string, unknown> {
  if (mode !== "reskin") return params
  const out: Record<string, unknown> = { ...params }
  if (out.setting !== "custom") delete out.custom_setting
  else out.custom_setting = String(out.custom_setting ?? "").trim()
  out.notes = String(out.notes ?? "").trim()
  if (!out.notes) delete out.notes
  if (!Array.isArray(out.keep_names) || out.keep_names.length === 0) delete out.keep_names
  return out
}
