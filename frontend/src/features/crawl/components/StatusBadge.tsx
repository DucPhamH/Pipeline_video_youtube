import { StatusPill, type StatusTone } from "@/components/StatusPill"
import { useT } from "@/i18n"
import type { LifecycleStatus } from "../../../api/types"

const LIFECYCLE_TONE: Record<LifecycleStatus, StatusTone> = {
  discovered: "info",
  crawling: "warning",
  fully_crawled: "success",
  translating: "info",
  ready_for_video: "success",
  produced: "success",
  rejected: "neutral",
  error: "danger",
}

/** Trạng thái vòng đời truyện — luôn qua StatusPill (crawling = chấm nhịp thở). */
export function StatusBadge({ status, className }: { status: LifecycleStatus; className?: string }) {
  const t = useT()
  return (
    <StatusPill
      status={status}
      label={t(`lifecycle.${status}`) || status}
      tone={LIFECYCLE_TONE[status] ?? "neutral"}
      live={status === "crawling"}
      className={className}
    />
  )
}

const CHAPTER_TONE: Record<string, StatusTone> = {
  pending: "info",
  crawled: "success",
  failed: "danger",
  unsupported: "neutral",
}

/** Trạng thái 1 chương (pending / crawled / failed / unsupported). */
export function ChapterStatusPill({ status }: { status: string }) {
  const t = useT()
  const label =
    status === "pending"
      ? t("novel.statusPending")
      : status === "crawled"
        ? t("novel.statusCrawled")
        : status === "failed"
          ? t("novel.statusError")
          : status
  return <StatusPill status={status} label={label} tone={CHAPTER_TONE[status] ?? "neutral"} live={false} />
}
