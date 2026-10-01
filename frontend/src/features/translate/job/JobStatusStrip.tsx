import { AlertTriangle, Flag, RotateCcw, WifiOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { StatusPill } from "@/components/StatusPill"
import { useT } from "@/i18n"
import { friendlyError } from "../errorText"
import { useStatusLabels } from "../hooks/useStatusLabels"
import type { Job } from "../types"

/** Dải trạng thái dính dưới header: trạng thái, model, tiến độ, cờ QA. */
export function JobStatusStrip({
  job,
  active,
  flaggedCount,
  connectionLost,
  quotaError,
  busy,
  onRetranslateFlagged,
  onShowFlagged,
}: {
  job: Job
  active: boolean
  flaggedCount: number
  connectionLost: boolean
  quotaError: boolean
  busy: boolean
  onRetranslateFlagged: () => void
  onShowFlagged: () => void
}) {
  const t = useT()
  const { jobStatusLabel } = useStatusLabels()
  const pct = job.total_segments > 0 ? Math.round((job.done_segments / job.total_segments) * 100) : 0
  const slots = job.provider_slots?.length ?? 0
  const tone = job.status === "failed" ? "danger" : "translate"

  return (
    <div className="sticky top-14 z-20 -mx-4 border-y border-border bg-card/95 px-4 py-3.5 backdrop-blur-sm sm:-mx-6 sm:px-6 lg:top-0 lg:mx-0 lg:rounded-2xl lg:border lg:px-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-5">
        <div className="flex min-w-0 shrink-0 items-center gap-2.5">
          <StatusPill status={job.status} label={jobStatusLabel(job.status)} live={active && job.status === "running"} />
          <span className="truncate font-mono text-[13px] text-muted-foreground">
            {job.model}
            {slots >= 2 ? ` · ${t("translate.job.aiSlots", { count: slots })}` : ""}
          </span>
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex items-baseline gap-2 text-[13px]">
            <span className="font-semibold">
              {t("translate.job.chaptersOf", { done: job.done_segments, total: job.total_segments })}
            </span>
            {job.failed_segments > 0 ? (
              <span className="text-danger">· {t("translate.job.failedCount", { count: job.failed_segments })}</span>
            ) : null}
            <span className="ml-auto font-mono text-muted-foreground tabular-nums">{pct}%</span>
          </div>
          <Progress
            value={pct}
            tone={tone}
            live={active}
            label={t("translate.job.chaptersOf", { done: job.done_segments, total: job.total_segments })}
          />
        </div>

        {flaggedCount > 0 ? (
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={onShowFlagged}
              className="inline-flex h-6 items-center gap-1.5 rounded-full bg-danger-soft px-2.5 text-xs font-semibold text-danger transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <Flag className="size-3" aria-hidden />
              {t("translate.job.flaggedCount", { count: flaggedCount })}
            </button>
            <Button type="button" variant="outline" size="sm" disabled={busy || active} onClick={onRetranslateFlagged}>
              <RotateCcw aria-hidden />
              {t("translate.retranslateFlaggedCount", { count: flaggedCount })}
            </Button>
          </div>
        ) : null}
      </div>

      {job.error || quotaError || connectionLost ? (
        <div className="mt-3 space-y-1.5">
          {connectionLost ? (
            <p role="status" className="flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning">
              <WifiOff className="size-4 shrink-0" aria-hidden />
              {t("translate.pollRetrying")}
            </p>
          ) : null}
          {job.error ? (
            <p className="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {friendlyError(job.error, t)}
            </p>
          ) : null}
          {quotaError ? (
            <p className="rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning">{t("translate.quotaErrorBanner")}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
