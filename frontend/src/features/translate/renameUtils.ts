/** Helper không phải component cho bảng tên / bảng đổi vỏ. */
import { toast } from "sonner"
import { ApiError } from "@/api/client"
import { useT } from "@/i18n"
import type { TranslateFn } from "@/i18n/types"
import { translateApi } from "./api"
import { friendlyError } from "./errorText"
import type { AiProvider, NameKind, RenameResult } from "./types"

export const NAME_KINDS: NameKind[] = ["character", "place", "term", "other", ""]

export function useNameKindLabel() {
  const t = useT()
  return (k: string) => (k ? t(`translate.nameKind_${k}`) : t("translate.nameKindNone"))
}

/** Thông báo lỗi API; 409 = có job đang chạy (backend chặn ghi đè chương). */
export function renameErrorText(err: unknown, t: TranslateFn): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return t("translate.namesJobRunning")
    if (err.status === 404) return t("translate.namesApiMissing")
    return friendlyError(err.message, t)
  }
  return t("app.unknownError")
}

/** Toast sau khi áp dụng, kèm nút Hoàn tác batch vừa tạo. */
export function toastApplied(
  t: TranslateFn,
  workId: number,
  result: RenameResult,
  onUndone: () => void,
) {
  const msg = t("translate.renameApplied", {
    count: result.total_replacements,
    segments: result.per_term.reduce((n, p) => n + p.segments, 0),
  })
  const batchId = result.batch_id
  toast.success(msg, {
    action:
      batchId != null
        ? {
            label: t("translate.renameUndo"),
            onClick: () => {
              translateApi
                .undoRenameBatch(workId, batchId)
                .then((r) => {
                  toast.success(t("translate.renameUndone", { restored: r.restored, skipped: r.skipped }))
                  onUndone()
                })
                .catch((err) => toast.error(renameErrorText(err, t)))
            },
          }
        : undefined,
  })
}

/** Mặc định chọn AI thật đầu tiên (tránh Mock). */
export function preferredProviderId(list: AiProvider[]): number | null {
  return list.find((p) => p.kind !== "mock")?.id ?? list[0]?.id ?? null
}
