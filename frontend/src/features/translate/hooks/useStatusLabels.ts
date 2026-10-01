/** Nhãn trạng thái đã dịch (job / segment / variant) — không hiện enum thô ra UI. */
import { useT } from "@/i18n"

export function useStatusLabels() {
  const t = useT()

  function jobStatusLabel(status: string | null | undefined): string {
    if (status === "queued") return t("translate.statusQueued")
    if (status === "running") return t("translate.statusRunning")
    if (status === "completed") return t("translate.statusCompleted")
    if (status === "failed") return t("translate.statusFailed")
    if (status === "cancelled") return t("translate.statusCancelled")
    return status ?? ""
  }

  function segmentStatusLabel(status: string): string {
    if (status === "pending" || status === "queued") return t("translate.filterPending")
    if (status === "running") return t("translate.statusRunning")
    if (status === "done" || status === "skipped_cache") return t("translate.filterDone")
    if (status === "failed") return t("translate.filterFailed")
    if (status === "cancelled") return t("translate.statusCancelled")
    if (status === "skipped") return t("translate.statusSkipped")
    return status
  }

  function variantStatusLabel(status: string): string {
    if (status === "pending") return t("translate.variantStatusPending")
    if (status === "ready") return t("translate.variantStatusReady")
    if (status === "cancelled") return t("translate.statusCancelled")
    return jobStatusLabel(status)
  }

  return { jobStatusLabel, segmentStatusLabel, variantStatusLabel }
}
