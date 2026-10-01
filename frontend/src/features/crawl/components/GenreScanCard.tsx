import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, CircleSlash, Layers, Radar } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { EmptyState } from "@/components/EmptyState"
import { StatusPill } from "@/components/StatusPill"
import { PageSkeleton } from "@/components/Skeleton"
import { useT } from "@/i18n"
import { queryKeys } from "@/lib/query-client"
import { cn } from "@/lib/utils"
import { ApiError } from "../../../api/client"
import type { Genre, GenreProgress } from "../../../api/types"
import type { GenreScan } from "./useGenreScan"
import { crawlApi } from "../api"

const PROGRESS_POLL_MS = 1000
const NONE_VALUE = "__none__"

export function GenreScanCard({ scan }: { scan: GenreScan }) {
  const t = useT()
  const { query, genres, active, isRunning } = scan

  if (query.error) {
    return (
      <p className="text-sm text-destructive">
        {query.error instanceof ApiError ? query.error.message : t("app.unknownError")}
      </p>
    )
  }
  if (query.isLoading || !genres) return <PageSkeleton withHeader={false} />
  if (genres.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed bg-card">
        <EmptyState icon={Layers} tone="collect" title={t("site.genreEmpty")} />
      </div>
    )
  }

  const value = active ? String(active.id) : NONE_VALUE

  return (
    <div className="space-y-4 rounded-2xl border bg-card p-5 shadow-[0_1px_2px_rgb(16_22_20/0.04)]">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0 flex-1 space-y-2">
          <Label htmlFor="genre-select" className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
            {t("site.genreCount", { count: genres.length })}
          </Label>
          <Select value={value} onValueChange={scan.select} disabled={isRunning}>
            <SelectTrigger id="genre-select" className="h-11 w-full max-w-xl text-[15px]">
              <SelectValue>
                {(v: string) =>
                  v === NONE_VALUE
                    ? t("site.genreNoneSelected")
                    : (genres.find((o) => String(o.id) === v)?.label ?? v)
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE_VALUE}>{t("site.genreNoneSelected")}</SelectItem>
              {genres.map((opt) => (
                <SelectItem key={opt.id} value={String(opt.id)}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {active ? (
            <p className="truncate font-mono text-xs text-muted-foreground" title={active.list_url}>
              {active.list_url}
            </p>
          ) : null}
        </div>
        {isRunning ? (
          <Button variant="outline" onClick={scan.cancel} disabled={!active || scan.cancelPending}>
            {scan.cancelPending ? t("site.stopping") : t("site.stopScan")}
          </Button>
        ) : null}
      </div>
      {active ? (
        <RunStatus genre={active} />
      ) : (
        <p className="text-sm text-muted-foreground">{t("site.genreNotSelectedYet")}</p>
      )}
    </div>
  )
}

function RunStatus({ genre }: { genre: Genre }) {
  const t = useT()
  const { data: progressPayload } = useQuery({
    queryKey: queryKeys.genreProgress(genre.id),
    queryFn: () => crawlApi.getGenreProgress(genre.id),
    enabled: genre.last_run_status === "running",
    refetchInterval: genre.last_run_status === "running" ? PROGRESS_POLL_MS : false,
  })
  const progress = progressPayload?.progress ?? null

  if (genre.last_run_status === "idle") {
    return <p className="text-sm text-muted-foreground">{t("site.genreNeverRun")}</p>
  }
  if (genre.last_run_status === "running") {
    return <LiveScanProgress genre={genre} progress={progress} />
  }
  const finishedAt = genre.last_run_finished_at ? formatTime(genre.last_run_finished_at) : ""
  const isError = genre.last_run_status === "error"
  const isCancelled = genre.last_run_status === "cancelled"
  const statusLabel = isCancelled ? t("site.statusCancelled") : isError ? t("site.statusError") : t("site.statusDone")
  const messages = (genre.last_run_messages ?? "").split("\n").filter(Boolean)
  const Icon = isError ? AlertTriangle : isCancelled ? CircleSlash : CheckCircle2

  return (
    <Alert
      variant={isError ? "destructive" : "default"}
      className={cn(
        "gap-y-2 px-4 py-3.5",
        isError ? "border-danger/25 bg-danger-soft" : isCancelled ? "bg-muted/50" : "border-success/20 bg-success-soft",
      )}
    >
      <Icon className={cn(isError ? "text-danger" : isCancelled ? "text-muted-foreground" : "text-success")} />
      <AlertTitle className="flex flex-wrap items-center gap-2 text-foreground">
        {t("site.lastRun", { status: statusLabel })}
        {finishedAt ? (
          <span className="font-mono text-xs font-normal text-muted-foreground">{finishedAt}</span>
        ) : null}
      </AlertTitle>
      <AlertDescription className="space-y-2 text-foreground">
        <div className="flex flex-wrap gap-2">
          <StatusPill status="done" tone="success" label={t("site.statAccepted", { count: genre.last_run_discovered ?? 0 })} />
          <StatusPill status="rejected" tone="neutral" label={t("site.statRejected", { count: genre.last_run_rejected ?? 0 })} />
          <StatusPill
            status="error"
            tone={(genre.last_run_errors ?? 0) > 0 ? "danger" : "neutral"}
            label={t("site.statErrors", { count: genre.last_run_errors ?? 0 })}
          />
        </div>
        {messages.length > 0 ? (
          <details className="group rounded-lg bg-card/70 px-3 py-2" open={isError && messages.length <= 3}>
            <summary className="cursor-pointer text-[13px] font-semibold">
              {t("site.runMessages", { count: messages.length })}
            </summary>
            <ul className="mt-2 max-h-48 list-disc space-y-1 overflow-y-auto pl-5 text-[13px] text-muted-foreground">
              {messages.map((m, i) => (
                <li key={i} className="break-words">
                  {m}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </AlertDescription>
    </Alert>
  )
}

function LiveScanProgress({ genre, progress }: { genre: Genre; progress: GenreProgress | null }) {
  const t = useT()
  const phaseLabel = useMemo(() => {
    const phase = progress?.phase ?? ""
    const labels: Record<string, string> = {
      listing: t("site.phaseList"),
      evaluating: t("site.phaseEvaluate"),
      crawling: t("site.phaseCrawl"),
      done: t("site.phaseDone"),
      error: t("site.phaseError"),
      cancelled: t("site.phaseCancelled"),
    }
    return labels[phase] ?? t("site.scanning")
  }, [progress?.phase, t])

  const scanWindow = progress?.scan_window || 0
  const discovered = progress?.discovered ?? 0
  const rejected = progress?.rejected ?? 0
  const errors = progress?.errors ?? 0
  const page = progress?.page ?? 0
  const maxPages = progress?.max_pages ?? 0
  const chapterIndex = progress?.chapter_index ?? 0
  const chapterTotal = progress?.chapter_total ?? 0

  const goalPct = scanWindow > 0 ? Math.min(100, Math.round((discovered / scanWindow) * 100)) : null
  const chapterPct = chapterTotal > 0 ? Math.min(100, Math.round((chapterIndex / chapterTotal) * 100)) : null

  return (
    <div className="space-y-4 rounded-xl bg-stage-collect-soft/70 p-4 ring-1 ring-stage-collect/15">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <p className="flex items-center gap-2 font-semibold text-foreground">
          <Radar className="size-4 text-stage-collect" aria-hidden />
          {phaseLabel}
          {genre.last_run_started_at ? (
            <span className="font-normal text-muted-foreground">
              {t("site.scanningFrom", { time: formatTime(genre.last_run_started_at) })}
            </span>
          ) : null}
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-xs text-muted-foreground tabular-nums">
            {page > 0 ? t("site.pageProgress", { page, maxPages: maxPages > 0 ? maxPages : "?" }) : "…"}
          </span>
          <StatusPill status="done" tone="success" label={`✓ ${discovered}${scanWindow ? `/${scanWindow}` : ""}`} />
          <StatusPill status="rejected" tone="neutral" label={`✗ ${rejected}`} />
          <StatusPill status="error" tone={errors > 0 ? "danger" : "neutral"} label={`⚠ ${errors}`} />
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between text-[13px] text-muted-foreground">
          <span>{t("site.acceptProgress")}</span>
          {goalPct !== null ? (
            <span className="font-mono tabular-nums">
              {discovered}/{scanWindow} ({goalPct}%)
            </span>
          ) : null}
        </div>
        <Progress value={goalPct} tone="collect" live label={t("site.acceptProgress")} />
      </div>

      {progress?.novel_title ? (
        <div className="space-y-1.5 rounded-lg bg-card/70 p-3">
          <p className="truncate text-sm font-medium text-foreground" title={progress.novel_title}>
            → {progress.novel_title}
          </p>
          {chapterPct !== null ? (
            <>
              <div className="flex justify-between text-[13px] text-muted-foreground">
                <span>{t("site.chapterCrawl")}</span>
                <span className="font-mono tabular-nums">
                  {chapterIndex}/{chapterTotal} ({chapterPct}%)
                </span>
              </div>
              <Progress value={chapterPct} tone="live" live size="sm" label={t("site.chapterCrawl")} />
            </>
          ) : progress.message ? (
            <p className="text-[13px] text-muted-foreground">{progress.message}</p>
          ) : null}
        </div>
      ) : (
        <p className="text-[13px] text-muted-foreground">{progress?.message || t("site.starting")}</p>
      )}
    </div>
  )
}

function formatTime(iso: string): string {
  try {
    return new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleTimeString()
  } catch {
    return iso
  }
}
