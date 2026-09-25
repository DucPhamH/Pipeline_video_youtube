import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import { KeyRound, Settings } from "lucide-react"
import { toast } from "sonner"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { PageHeader, PageShell, SegmentedTabs, Toolbar } from "@/components/PageChrome"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useT } from "@/i18n"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { queryKeys } from "@/lib/query-client"
import { ApiError } from "../../../api/client"
import type { Genre, GenreProgress, LifecycleStatus, Novel } from "../../../api/types"
import { crawlApi, perSiteSettingKey } from "../api"
import { AddNovelForm } from "../components/AddNovelForm"
import {
  GenericSessionInstructions,
  SessionGuidePanel,
} from "../components/SessionGuidePanel"
import { StatusBadge } from "../components/StatusBadge"
import { getSessionGuide } from "../sessionGuides"

// Trang chi tiết 1 SITE — Quét / URL / Thư viện (danh sách truyện tách riêng).
const POLL_INTERVAL_MS = 3000
const PROGRESS_POLL_MS = 1000
const PAGE_SIZE = 10
const NONE_VALUE = "__none__"
/** Mỗi site có ~5–15 thể loại — load hết 1 lần cho ô Select, không phân trang UI. */
const GENRE_SELECT_LIMIT = 100

type CrawlTab = "bulk" | "url" | "library"
type NovelOrigin = "all" | "scanned" | "manual"

export function SiteDetailPage() {
  const t = useT()
  const { sourceKey = "" } = useParams<{ sourceKey: string }>()
  const [tab, setTab] = useState<CrawlTab>("bulk")
  const [statusFilter, setStatusFilter] = useState<LifecycleStatus | "all">("all")
  const [genreFilter, setGenreFilter] = useState<number | "all">("all")
  const [search, setSearch] = useState("")
  const [novelOrigin, setNovelOrigin] = useState<NovelOrigin>("all")
  const [sessionOpen, setSessionOpen] = useState(false)

  const { data: sitesData } = useQuery({
    queryKey: queryKeys.sites({ limit: 100 }),
    queryFn: () => crawlApi.listSites({ limit: 100 }),
  })
  const siteName = sitesData?.items.find((s) => s.key === sourceKey)?.name ?? sourceKey
  const sessionGuide = getSessionGuide(sourceKey)

  const { data: libraryMeta } = useQuery({
    queryKey: ["novels", "library-meta", sourceKey],
    queryFn: async () => {
      const [all, errors] = await Promise.all([
        crawlApi.listNovels({ sourceKey, limit: 1, offset: 0 }),
        crawlApi.listNovels({ sourceKey, status: "error", limit: 1, offset: 0 }),
      ])
      return { total: all.total, errors: errors.total }
    },
    refetchInterval: (q) => ((q.state.data?.errors ?? 0) > 0 ? POLL_INTERVAL_MS : false),
  })

  const libraryLabel =
    libraryMeta && libraryMeta.errors > 0
      ? t("site.tabLibraryErrors", {
          count: libraryMeta.total,
          errors: libraryMeta.errors,
        })
      : t("site.tabLibrary", { count: libraryMeta?.total ?? 0 })

  return (
    <PageShell>
      <PageHeader
        eyebrow={
          <Link to="/sites" className="hover:text-foreground hover:underline">
            {t("common.backSites")}
          </Link>
        }
        title={siteName}
        description={t("site.pageDesc")}
        actions={
          <>
            <SiteSessionDialog sourceKey={sourceKey} open={sessionOpen} onOpenChange={setSessionOpen} />
            {tab !== "url" && <SiteSettingsDialog sourceKey={sourceKey} />}
          </>
        }
      />

      {sessionGuide && (
        <Alert className="border-amber-500/25 bg-amber-500/5">
          <AlertDescription className="text-sm">
            <strong>{t("site.sessionAlert")}</strong> {sessionGuide.summary}{" "}
            <button
              type="button"
              className="font-medium text-primary underline-offset-2 hover:underline"
              onClick={() => setSessionOpen(true)}
            >
              {t("site.sessionGuideLink")}
            </button>
          </AlertDescription>
        </Alert>
      )}

      <SegmentedTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "bulk", label: t("site.tabBulk") },
          { value: "url", label: t("site.tabUrl") },
          { value: "library", label: libraryLabel },
        ]}
      />

      {tab === "bulk" ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("site.bulkHint")}</p>
          <GenreSection sourceKey={sourceKey} />
        </div>
      ) : null}

      {tab === "url" ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("site.urlHint")}</p>
          <AddNovelForm sourceKey={sourceKey} />
        </div>
      ) : null}

      {tab === "library" ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("site.libraryHint")}</p>
          <div className="flex flex-wrap gap-2">
            {(["all", "scanned", "manual"] as const).map((origin) => (
              <Button
                key={origin}
                type="button"
                size="sm"
                variant={novelOrigin === origin ? "default" : "outline"}
                onClick={() => setNovelOrigin(origin)}
              >
                {origin === "all"
                  ? t("site.originAll")
                  : origin === "scanned"
                    ? t("site.originScanned")
                    : t("site.originManual")}
              </Button>
            ))}
          </div>
          <NovelsSection
            sourceKey={sourceKey}
            isManual={novelOrigin === "all" ? undefined : novelOrigin === "manual"}
            status={statusFilter}
            onStatusChange={setStatusFilter}
            genreFilter={genreFilter}
            onGenreFilterChange={setGenreFilter}
            search={search}
            onSearchChange={setSearch}
          />
        </div>
      ) : null}
    </PageShell>
  )
}

// ------------------------------------------------------------- Thể loại --
// "Quét nhiều" — chọn 1 thể loại/bảng xếp hạng, bấm Quét ngay để tự phát
// hiện NHIỀU truyện khớp tiêu chí ngắn+hoàn thành cùng lúc.

function GenreSection({ sourceKey }: { sourceKey: string }) {
  const t = useT()
  const queryClient = useQueryClient()
  const genreQueryKey = { sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }

  const { data, error, isLoading } = useQuery({
    queryKey: queryKeys.genres(genreQueryKey),
    queryFn: () => crawlApi.listGenres(genreQueryKey),
    refetchInterval: (q) =>
      q.state.data?.items.some((g) => g.last_run_status === "running") ? POLL_INTERVAL_MS : false,
  })

  const genres = data?.items ?? null

  const selectMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.toggleGenre(genreId, true),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.genres(genreQueryKey) })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const deselectMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.toggleGenre(genreId, false),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.genres(genreQueryKey) })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const runMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.runGenreNow(genreId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.genres(genreQueryKey) })
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
      toast.message(t("site.scanStarted"))
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const cancelMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.cancelGenreRun(genreId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.genres(genreQueryKey) })
      toast.message(t("site.scanCancelSent"))
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  if (error) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof ApiError ? error.message : t("app.unknownError")}
      </p>
    )
  }
  if (isLoading || !genres) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
  if (genres.length === 0) {
    return (
      <Alert>
        <AlertDescription>{t("site.genreEmpty")}</AlertDescription>
      </Alert>
    )
  }

  return (
    <GenreCard
      options={genres}
      onSelect={(id) => {
        if (!id || id === NONE_VALUE) {
          const active = genres.find((g) => g.enabled)
          if (active) deselectMutation.mutate(active.id)
          return
        }
        selectMutation.mutate(Number(id))
      }}
      onRunNow={(g) => runMutation.mutate(g.id)}
      onCancel={(g) => cancelMutation.mutate(g.id)}
      cancelPending={cancelMutation.isPending}
    />
  )
}

function GenreCard({
  options,
  onSelect,
  onRunNow,
  onCancel,
  cancelPending,
}: {
  options: Genre[]
  onSelect: (id: string | null) => void
  onRunNow: (genre: Genre) => void
  onCancel: (genre: Genre) => void
  cancelPending: boolean
}) {
  const t = useT()
  if (options.length === 0) return null

  const active = options.find((o) => o.enabled) ?? null
  const isRunning = active?.last_run_status === "running"
  const value = active ? String(active.id) : NONE_VALUE

  return (
    <Card className="overflow-hidden ring-border/70">
      <CardContent className="space-y-4 pt-1">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0 flex-1 space-y-2">
            <Label className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              {t("site.genreCount", { count: options.length })}
            </Label>
            <Select value={value} onValueChange={onSelect} disabled={isRunning}>
              <SelectTrigger className="h-11 w-full max-w-xl">
                <SelectValue>
                  {(v: string) =>
                    v === NONE_VALUE
                      ? t("site.genreNoneSelected")
                      : (options.find((o) => String(o.id) === v)?.label ?? v)
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE_VALUE}>{t("site.genreNoneSelected")}</SelectItem>
                {options.map((opt) => (
                  <SelectItem key={opt.id} value={String(opt.id)}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {active ? (
              <p className="truncate font-mono text-xs text-muted-foreground">{active.list_url}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {isRunning ? (
              <Button
                variant="outline"
                size="lg"
                onClick={() => active && onCancel(active)}
                disabled={!active || cancelPending}
              >
                {cancelPending ? t("site.stopping") : t("site.stopScan")}
              </Button>
            ) : null}
            <Button
              size="lg"
              onClick={() => active && onRunNow(active)}
              disabled={isRunning || !active}
            >
              {isRunning ? t("site.scanning") : t("site.scanNow")}
            </Button>
          </div>
        </div>
        {active ? (
          <RunStatus genre={active} />
        ) : (
          <p className="text-sm text-muted-foreground">{t("site.genreNotSelectedYet")}</p>
        )}
      </CardContent>
    </Card>
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
    return <p className="text-xs text-muted-foreground">{t("site.genreNeverRun")}</p>
  }
  if (genre.last_run_status === "running") {
    return <LiveScanProgress genre={genre} progress={progress} />
  }
  const finishedAt = genre.last_run_finished_at ? formatTime(genre.last_run_finished_at) : ""
  const statusLabel =
    genre.last_run_status === "cancelled"
      ? t("site.statusCancelled")
      : genre.last_run_status === "error"
        ? t("site.statusError")
        : t("site.statusDone")
  return (
    <Alert variant={genre.last_run_status === "error" ? "destructive" : "default"}>
      <AlertDescription>
        {t("site.lastRun", { status: statusLabel })}
        {finishedAt ? t("site.lastRunAt", { time: finishedAt }) : ""}:{" "}
        {t("site.lastRunStats", {
          discovered: genre.last_run_discovered ?? 0,
          rejected: genre.last_run_rejected ?? 0,
          errors: genre.last_run_errors ?? 0,
        })}
        {genre.last_run_messages && (
          <ul className="mt-1 list-disc pl-5">
            {genre.last_run_messages.split("\n").map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        )}
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

  const goalPct =
    scanWindow > 0 ? Math.min(100, Math.round((discovered / scanWindow) * 100)) : null
  const chapterPct =
    chapterTotal > 0 ? Math.min(100, Math.round((chapterIndex / chapterTotal) * 100)) : null

  return (
    <div className="space-y-4 rounded-xl border border-primary/20 bg-primary/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <p className="font-medium text-foreground">
          {phaseLabel}
          {genre.last_run_started_at ? (
            <span className="ml-2 font-normal text-muted-foreground">
              {t("site.scanningFrom", { time: formatTime(genre.last_run_started_at) })}
            </span>
          ) : null}
        </p>
        <p className="tabular-nums text-muted-foreground">
          {page > 0
            ? maxPages > 0
              ? t("site.pageProgress", { page, maxPages })
              : t("site.pageProgress", { page, maxPages: "?" })
            : "…"}
          {" · "}✓{discovered}
          {scanWindow ? `/${scanWindow}` : ""} ✗{rejected} ⚠{errors}
        </p>
      </div>

      {goalPct !== null && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{t("site.acceptProgress")}</span>
            <span className="tabular-nums">
              {discovered}/{scanWindow} ({goalPct}%)
            </span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-background/80 ring-1 ring-border/50">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${goalPct}%` }}
            />
          </div>
        </div>
      )}

      {progress?.novel_title ? (
        <div className="space-y-1.5">
          <p className="truncate text-sm text-foreground" title={progress.novel_title}>
            → {progress.novel_title}
          </p>
          {chapterPct !== null ? (
            <>
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{t("site.chapterCrawl")}</span>
                <span className="tabular-nums">
                  {chapterIndex}/{chapterTotal} ({chapterPct}%)
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-background/80 ring-1 ring-border/50">
                <div
                  className="h-full rounded-full bg-amber-500 transition-[width] duration-300"
                  style={{ width: `${chapterPct}%` }}
                />
              </div>
            </>
          ) : progress.message ? (
            <p className="text-xs text-muted-foreground">{progress.message}</p>
          ) : null}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {progress?.message || t("site.starting")}
        </p>
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

// -------------------------------------------------------------- Cài đặt --
// Setting quyết định CÁCH QUÉT của riêng site này (mục 9.0) — khác site
// khác có thể có tốc độ/độ dài truyện phổ biến khác nhau.

type SettingFieldDef =
  | { type: "number"; key: string; default: number; labelKey: string; hintKey: string }
  | {
      type: "select"
      key: string
      default: string
      labelKey: string
      hintKey: string
      options: Array<{ value: string; labelKey: string }>
    }

type SettingField =
  | { type: "number"; key: string; label: string; hint: string; default: number }
  | {
      type: "select"
      key: string
      label: string
      hint: string
      default: string
      options: Array<{ value: string; label: string }>
    }

const SITE_SETTING_FIELD_DEFS: SettingFieldDef[] = [
  {
    type: "number",
    key: "scan_window",
    default: 5,
    labelKey: "site.fieldScanWindow",
    hintKey: "site.fieldScanWindowHint",
  },
  {
    type: "number",
    key: "max_chapters_per_story",
    default: 50,
    labelKey: "site.fieldMaxChapters",
    hintKey: "site.fieldMaxChaptersHint",
  },
  {
    type: "number",
    key: "max_pages_per_scan",
    default: 3,
    labelKey: "site.fieldMaxPages",
    hintKey: "site.fieldMaxPages",
  },
  {
    type: "number",
    key: "max_consecutive_errors",
    default: 5,
    labelKey: "site.fieldMaxErrors",
    hintKey: "site.fieldMaxErrors",
  },
  {
    type: "select",
    key: "narration_filter",
    default: "first_person",
    labelKey: "site.fieldNarration",
    hintKey: "site.fieldNarrationHint",
    options: [
      { value: "any", labelKey: "site.optAny" },
      { value: "first_person", labelKey: "site.optFirstPerson" },
      { value: "third_person", labelKey: "site.optThirdPerson" },
    ],
  },
  {
    type: "select",
    key: "completion_filter",
    default: "completed_only",
    labelKey: "site.fieldCompletion",
    hintKey: "site.fieldCompletionHint",
    options: [
      { value: "completed_only", labelKey: "site.optCompleted" },
      { value: "ongoing_only", labelKey: "site.optOngoing" },
      { value: "any", labelKey: "site.optAny" },
    ],
  },
  {
    type: "select",
    key: "opencc_mode",
    default: "none",
    labelKey: "site.fieldOpencc",
    hintKey: "site.fieldOpenccHint",
    options: [
      { value: "none", labelKey: "site.optOpenccNone" },
      { value: "t2s", labelKey: "site.optOpenccT2s" },
      { value: "s2t", labelKey: "site.optOpenccS2t" },
      { value: "s2tw", labelKey: "site.optOpenccS2tw" },
      { value: "tw2s", labelKey: "site.optOpenccTw2s" },
    ],
  },
]

function SiteSessionDialog({
  sourceKey,
  open,
  onOpenChange,
}: {
  sourceKey: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const t = useT()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)

  // Luôn tải trạng thái phiên (không chỉ khi mở dialog) — để hiện badge "đã có" trên nút.
  const { data: session, isFetching } = useQuery({
    queryKey: ["site-session", sourceKey],
    queryFn: () => crawlApi.getSiteSession(sourceKey),
  })

  const cookieValue = draft ?? session?.cookie_header ?? ""
  const guide = getSessionGuide(sourceKey)

  const saveMutation = useMutation({
    mutationFn: (cookieHeader: string) => crawlApi.saveSiteSession(sourceKey, cookieHeader),
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: ["site-session", sourceKey] })
      toast.success(t("site.sessionSaved"))
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const probeMutation = useMutation({
    mutationFn: async () => {
      if (draft !== null && draft !== (session?.cookie_header ?? "")) {
        await crawlApi.saveSiteSession(sourceKey, draft)
        setDraft(null)
      }
      return crawlApi.probeSiteSession(sourceKey)
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["site-session", sourceKey] })
      if (result.ok) toast.success(result.message)
      else toast.error(result.message)
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => onOpenChange(true)}>
        <KeyRound className="size-4" />
        {t("site.sessionBtn")}
        {session?.configured ? (
          <span className="text-xs text-emerald-700 dark:text-emerald-400">{t("site.sessionHas")}</span>
        ) : (session?.missing_required_cookies?.length ?? 0) > 0 || guide ? (
          <span className="text-xs text-amber-700 dark:text-amber-400">{t("site.sessionNeed")}</span>
        ) : null}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          onOpenChange(next)
          if (!next) setDraft(null)
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-x-hidden overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t("site.sessionDialogTitle")}</DialogTitle>
            <DialogDescription>{t("site.sessionDialogDesc")}</DialogDescription>
          </DialogHeader>
          {guide ? <SessionGuidePanel guide={guide} /> : <GenericSessionInstructions />}
          {isFetching && !session ? (
            <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
          ) : (
            <div className="space-y-2">
              <Label htmlFor={`${sourceKey}-session-cookie`}>{t("site.cookieHeader")}</Label>
              <Textarea
                id={`${sourceKey}-session-cookie`}
                rows={8}
                value={cookieValue}
                placeholder={t("site.cookiePlaceholder")}
                onChange={(e) => setDraft(e.target.value)}
                spellCheck={false}
                wrap="soft"
                className="max-h-48 overflow-x-hidden overflow-y-auto font-mono text-xs break-all whitespace-pre-wrap"
              />
              {session?.configured && (
                <p className="text-xs text-muted-foreground">
                  {t("site.cookieSaving", {
                    count: session.cookie_names.length,
                    names:
                      session.cookie_names.slice(0, 8).join(", ") +
                      (session.cookie_names.length > 8 ? "…" : ""),
                  })}
                </p>
              )}
              {session && (session.missing_required_cookies?.length ?? 0) > 0 && (
                <p className="text-xs text-amber-700 dark:text-amber-300">
                  {t("site.cookieMissingRequired", {
                    names: session.missing_required_cookies.join(", "),
                  })}
                </p>
              )}
            </div>
          )}
          <DialogFooter className="gap-2 sm:justify-between">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDraft("")
                saveMutation.mutate("")
              }}
              disabled={saveMutation.isPending}
            >
              {t("site.clearSession")}
            </Button>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => probeMutation.mutate()}
                disabled={probeMutation.isPending || saveMutation.isPending}
              >
                {probeMutation.isPending ? t("site.probing") : t("site.probeSession")}
              </Button>
              <Button
                type="button"
                onClick={() => saveMutation.mutate(cookieValue)}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? t("common.saving") : t("common.save")}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

type SiteSettingValue = number | string | boolean

const DAILY_SETTING_DEFAULTS: Record<string, SiteSettingValue> = {
  daily_enabled: false,
  daily_hour: 6,
  daily_minute: 0,
  daily_genre_key: "",
  http_proxy: "",
}

/** Preset lọc quét — chỉ đụng field filter, giữ nguyên lịch daily. */
const SCAN_FILTER_PRESETS: Array<{
  id: string
  labelKey: string
  hintKey: string
  values: Record<string, SiteSettingValue>
}> = [
  {
    id: "short_video_cn",
    labelKey: "site.presetShortVideo",
    hintKey: "site.presetShortVideoHint",
    values: {
      scan_window: 5,
      max_chapters_per_story: 40,
      max_pages_per_scan: 3,
      max_consecutive_errors: 5,
      narration_filter: "first_person",
      completion_filter: "completed_only",
    },
  },
  {
    id: "short_any_voice",
    labelKey: "site.presetShortAny",
    hintKey: "site.presetShortAnyHint",
    values: {
      scan_window: 5,
      max_chapters_per_story: 50,
      max_pages_per_scan: 3,
      max_consecutive_errors: 5,
      narration_filter: "any",
      completion_filter: "completed_only",
    },
  },
  {
    id: "wider",
    labelKey: "site.presetWider",
    hintKey: "site.presetWiderHint",
    values: {
      scan_window: 8,
      max_chapters_per_story: 80,
      max_pages_per_scan: 5,
      max_consecutive_errors: 8,
      narration_filter: "any",
      completion_filter: "completed_only",
    },
  },
]

function SiteSettingsDialog({ sourceKey }: { sourceKey: string }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Record<string, SiteSettingValue> | null>(null)
  const [open, setOpen] = useState(false)

  const siteSettingFields = useMemo((): SettingField[] => {
    return SITE_SETTING_FIELD_DEFS.map((def) => {
      if (def.type === "number") {
        return {
          type: "number",
          key: def.key,
          label: t(def.labelKey),
          hint: t(def.hintKey),
          default: def.default,
        }
      }
      return {
        type: "select",
        key: def.key,
        label: t(def.labelKey),
        hint: t(def.hintKey),
        default: def.default,
        options: def.options.map((opt) => ({ value: opt.value, label: t(opt.labelKey) })),
      }
    })
  }, [t])

  const { data: settings } = useQuery({
    queryKey: queryKeys.settings,
    queryFn: () => crawlApi.getSettings(),
    enabled: open,
  })

  const { data: genresData } = useQuery({
    queryKey: queryKeys.genres({ sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }),
    queryFn: () => crawlApi.listGenres({ sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }),
    enabled: open,
  })
  const genres = genresData?.items ?? []

  const values =
    draft ??
    (settings
      ? Object.fromEntries([
          ...siteSettingFields.map((field) => {
            const raw = settings.values[perSiteSettingKey(field.key, sourceKey)]
            return [field.key, (raw as SiteSettingValue | undefined) ?? field.default]
          }),
          ...Object.entries(DAILY_SETTING_DEFAULTS).map(([key, def]) => {
            const raw = settings.values[perSiteSettingKey(key, sourceKey)]
            return [key, (raw as SiteSettingValue | undefined) ?? def]
          }),
        ])
      : null)

  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, SiteSettingValue>) => crawlApi.updateSettings(payload),
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings })
      toast.success(t("site.settingsSaved"))
      setOpen(false)
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  function patchDraft(key: string, value: SiteSettingValue) {
    setDraft((prev) => ({ ...(prev ?? values ?? {}), [key]: value }))
  }

  function handleNumberChange(key: string, raw: string) {
    const n = Number(raw)
    if (!Number.isFinite(n)) return
    patchDraft(key, n)
  }

  function handleSelectChange(key: string, v: string | null) {
    if (!v) return
    patchDraft(key, v)
  }

  function applyScanPreset(presetId: string) {
    const preset = SCAN_FILTER_PRESETS.find((p) => p.id === presetId)
    if (!preset) return
    setDraft((prev) => ({
      ...(prev ?? values ?? {}),
      ...preset.values,
    }))
    toast.message(t("site.presetApplied", { name: t(preset.labelKey) }))
  }

  function handleTimeChange(raw: string) {
    const [h, m] = raw.split(":").map((p) => Number(p))
    if (!Number.isFinite(h) || !Number.isFinite(m)) return
    setDraft((prev) => ({
      ...(prev ?? values ?? {}),
      daily_hour: Math.min(23, Math.max(0, Math.trunc(h))),
      daily_minute: Math.min(59, Math.max(0, Math.trunc(m))),
    }))
  }

  function handleSave() {
    if (!values) return
    const payload: Record<string, SiteSettingValue> = {}
    for (const key of Object.keys(values)) {
      payload[perSiteSettingKey(key, sourceKey)] = values[key] as SiteSettingValue
    }
    saveMutation.mutate(payload)
  }

  const dailyEnabled = Boolean(values?.daily_enabled)
  const timeValue = values
    ? `${String(Number(values.daily_hour ?? 6)).padStart(2, "0")}:${String(Number(values.daily_minute ?? 0)).padStart(2, "0")}`
    : "06:00"
  const genreKeyValue = String(values?.daily_genre_key ?? "") || NONE_VALUE

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Settings className="size-4" />
        {t("site.settingsTitle")}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) setDraft(null)
        }}
      >
        <DialogContent className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
          <DialogHeader className="shrink-0 space-y-1 border-b px-6 py-5 pr-12">
            <DialogTitle className="text-lg">{t("site.settingsDialogTitle")}</DialogTitle>
            <DialogDescription>{t("site.settingsDialogDesc")}</DialogDescription>
          </DialogHeader>

          {values === null ? (
            <p className="px-6 py-10 text-sm text-muted-foreground">{t("app.loading")}</p>
          ) : (
            <div className="min-h-0 flex-1 space-y-8 overflow-y-auto px-6 py-5">
              <section className="space-y-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold tracking-tight">{t("site.dailySectionTitle")}</h3>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {t("site.dailySectionHint")}
                  </p>
                </div>

                <div
                  className={
                    dailyEnabled
                      ? "rounded-lg border border-primary/25 bg-primary/5 p-4"
                      : "rounded-lg border bg-muted/30 p-4"
                  }
                >
                  <label className="flex cursor-pointer items-start gap-3">
                    <Checkbox
                      className="mt-0.5"
                      checked={dailyEnabled}
                      onCheckedChange={(checked) => patchDraft("daily_enabled", checked === true)}
                    />
                    <span className="space-y-0.5">
                      <span className="block text-sm font-medium">{t("site.dailyEnabled")}</span>
                      <span className="block text-xs text-muted-foreground">
                        {t("site.dailyEnabledHint")}
                      </span>
                    </span>
                  </label>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor={`${sourceKey}-daily-time`}>{t("site.dailyTime")}</Label>
                    <Input
                      id={`${sourceKey}-daily-time`}
                      type="time"
                      value={timeValue}
                      disabled={!dailyEnabled}
                      onChange={(e) => handleTimeChange(e.target.value)}
                      className="h-10 w-full"
                    />
                    <p className="text-xs text-muted-foreground">{t("site.dailyTimeHint")}</p>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`${sourceKey}-scan_window`}>{t("site.fieldScanWindow")}</Label>
                    <Input
                      id={`${sourceKey}-scan_window`}
                      type="number"
                      min={1}
                      value={Number(values.scan_window ?? 5)}
                      onChange={(e) => handleNumberChange("scan_window", e.target.value)}
                      className="h-10 w-full"
                    />
                    <p className="text-xs text-muted-foreground">{t("site.fieldScanWindowHint")}</p>
                  </div>
                  <div className="space-y-1.5 sm:col-span-2">
                    <Label htmlFor={`${sourceKey}-daily-genre`}>{t("site.dailyGenre")}</Label>
                    <Select
                      value={genreKeyValue}
                      disabled={!dailyEnabled}
                      onValueChange={(v) =>
                        handleSelectChange("daily_genre_key", v === NONE_VALUE ? "" : (v ?? ""))
                      }
                    >
                      <SelectTrigger id={`${sourceKey}-daily-genre`} className="h-10 w-full">
                        <SelectValue>
                          {(v: string) =>
                            v === NONE_VALUE
                              ? t("site.dailyGenreNone")
                              : (genres.find((g) => g.genre_key === v)?.label ?? v)
                          }
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE_VALUE}>{t("site.dailyGenreNone")}</SelectItem>
                        {genres.map((g) => (
                          <SelectItem key={g.genre_key} value={g.genre_key}>
                            {g.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">{t("site.dailyGenreHint")}</p>
                  </div>
                </div>
              </section>

              <section className="space-y-4 border-t pt-6">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold tracking-tight">{t("site.proxySectionTitle")}</h3>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {t("site.proxySectionHint")}
                  </p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`${sourceKey}-http_proxy`}>{t("site.fieldHttpProxy")}</Label>
                  <Input
                    id={`${sourceKey}-http_proxy`}
                    type="text"
                    value={String(values.http_proxy ?? "")}
                    onChange={(e) => patchDraft("http_proxy", e.target.value)}
                    placeholder="http://127.0.0.1:7890"
                    className="h-10 w-full font-mono text-sm"
                  />
                  <p className="text-xs text-muted-foreground">{t("site.fieldHttpProxyHint")}</p>
                </div>
              </section>

              <section className="space-y-4 border-t pt-6">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold tracking-tight">{t("site.filtersSectionTitle")}</h3>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {t("site.filtersSectionHint")}
                  </p>
                </div>
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">{t("site.presetTitle")}</p>
                  <div className="flex flex-wrap gap-2">
                    {SCAN_FILTER_PRESETS.map((preset) => (
                      <Button
                        key={preset.id}
                        type="button"
                        size="sm"
                        variant="outline"
                        title={t(preset.hintKey)}
                        onClick={() => applyScanPreset(preset.id)}
                      >
                        {t(preset.labelKey)}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  {siteSettingFields
                    .filter((field) => field.key !== "scan_window")
                    .map((field) => (
                      <div
                        key={field.key}
                        className={
                          field.type === "select" ? "space-y-1.5 sm:col-span-2" : "space-y-1.5"
                        }
                      >
                        <Label htmlFor={`${sourceKey}-${field.key}`}>{field.label}</Label>
                        {field.type === "number" ? (
                          <Input
                            id={`${sourceKey}-${field.key}`}
                            type="number"
                            min={1}
                            value={Number(values[field.key] ?? field.default)}
                            onChange={(e) => handleNumberChange(field.key, e.target.value)}
                            className="h-10 w-full"
                          />
                        ) : (
                          <Select
                            value={String(values[field.key] ?? field.default)}
                            onValueChange={(v) => handleSelectChange(field.key, v)}
                          >
                            <SelectTrigger id={`${sourceKey}-${field.key}`} className="h-10 w-full">
                              <SelectValue>
                                {(v: string) =>
                                  field.options.find((o) => o.value === v)?.label ?? v
                                }
                              </SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              {field.options.map((opt) => (
                                <SelectItem key={opt.value} value={opt.value}>
                                  {opt.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )}
                        <p className="text-xs text-muted-foreground">{field.hint}</p>
                      </div>
                    ))}
                </div>
              </section>
            </div>
          )}

          <DialogFooter className="-mx-0 -mb-0 rounded-none border-t px-6 py-4">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="button" onClick={handleSave} disabled={saveMutation.isPending || values === null}>
              {saveMutation.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

// -------------------------------------------------------------- Truyện --
// Danh sách truyện đã crawl (từ "Quét ngay" HOẶC từ "Thêm truyện bằng
// URL" ở trên) — tự phân trang, lọc theo trạng thái + tên.

const LIFECYCLE_STATUS_VALUES: Array<LifecycleStatus | "all"> = [
  "all",
  "discovered",
  "crawling",
  "fully_crawled",
  // translating / ready_for_video / produced — phase 2 (chưa ship) — không hiện filter
  "rejected",
  "error",
]

function canRecrawl(novel: Novel): boolean {
  // Nút Thử lại / Đồng bộ + chọn hàng loạt — rejected dùng "Buộc nhận" riêng.
  return novel.lifecycle_status === "error" || novel.lifecycle_status === "fully_crawled"
}

function canExportNovel(novel: Novel): boolean {
  return novel.lifecycle_status === "fully_crawled"
}

function canSelectNovel(novel: Novel): boolean {
  return canRecrawl(novel) || canExportNovel(novel)
}

const GENRE_FILTER_ALL = "__all__"

function NovelsSection({
  sourceKey,
  isManual,
  status,
  onStatusChange,
  genreFilter,
  onGenreFilterChange,
  search,
  onSearchChange,
}: {
  sourceKey: string
  /** undefined = mọi nguồn; false = quét; true = URL tay */
  isManual?: boolean
  status: LifecycleStatus | "all"
  onStatusChange: (v: LifecycleStatus | "all") => void
  genreFilter: number | "all"
  onGenreFilterChange: (v: number | "all") => void
  search: string
  onSearchChange: (v: string) => void
}) {
  const t = useT()
  const queryClient = useQueryClient()
  const [offset, setOffset] = useState(0)

  const statusOptions = useMemo(
    () =>
      LIFECYCLE_STATUS_VALUES.map((value) => ({
        value,
        label: t(`lifecycle.${value}`),
      })),
    [t],
  )
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const debouncedSearch = useDebouncedValue(search.trim(), 350)
  const effectiveStatus = status === "all" ? undefined : status
  const effectiveSearch = debouncedSearch || undefined
  const effectiveGenreId = isManual !== true && genreFilter !== "all" ? genreFilter : undefined

  const { data: genresData } = useQuery({
    queryKey: queryKeys.genres({ sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }),
    queryFn: () => crawlApi.listGenres({ sourceKey, limit: GENRE_SELECT_LIMIT }),
    enabled: isManual !== true,
  })
  const genreById = useMemo(() => {
    const map = new Map<number, Genre>()
    for (const g of genresData?.items ?? []) map.set(g.id, g)
    return map
  }, [genresData])

  // Đổi filter → về trang đầu NGAY TRONG RENDER, không qua effect (sửa
  // 17/9/2026, giống NovelDetailPage.tsx: bản effect cũ khiến query chạy 1
  // lần thừa với offset CŨ ngay khi đổi filter trước khi effect kịp
  // setOffset(0), oxlint bắt đúng chỗ này — `react(set-state-in-effect)`).
  const filterKey = `${sourceKey}|${String(isManual)}|${effectiveStatus}|${effectiveGenreId}|${effectiveSearch}`
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey)
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey)
    setOffset(0)
  }

  // Xoá selection khi đổi filter HOẶC đổi trang (giữ đúng hành vi cũ — 2
  // effect trước gộp lại thành 1 lần so sánh khoá duy nhất).
  const selectionResetKey = `${filterKey}|${offset}`
  const [prevSelectionResetKey, setPrevSelectionResetKey] = useState(selectionResetKey)
  if (selectionResetKey !== prevSelectionResetKey) {
    setPrevSelectionResetKey(selectionResetKey)
    setSelectedIds(new Set())
  }

  const listParams = {
    sourceKey,
    status: effectiveStatus,
    search: effectiveSearch,
    isManual,
    genreId: effectiveGenreId,
    limit: PAGE_SIZE,
    offset,
  }

  const { data, error, isFetching } = useQuery({
    queryKey: queryKeys.novels(listParams),
    queryFn: () => crawlApi.listNovels(listParams),
    placeholderData: (prev) => prev,
    refetchInterval: (q) =>
      q.state.data?.items.some((n) => n.lifecycle_status === "crawling") ? POLL_INTERVAL_MS : false,
  })

  const novels = data?.items ?? null
  const total = data?.total ?? 0
  const selectableOnPage = useMemo(
    () => (novels ?? []).filter(canSelectNovel),
    [novels],
  )
  const allSelectableSelected =
    selectableOnPage.length > 0 && selectableOnPage.every((n) => selectedIds.has(n.id))
  const someSelectableSelected =
    selectableOnPage.some((n) => selectedIds.has(n.id)) && !allSelectableSelected
  const selectedRetryable = useMemo(
    () => (novels ?? []).filter((n) => selectedIds.has(n.id) && canRecrawl(n)),
    [novels, selectedIds],
  )
  const selectedExportable = useMemo(
    () => (novels ?? []).filter((n) => selectedIds.has(n.id) && canExportNovel(n)),
    [novels, selectedIds],
  )

  const errorCountParams = {
    sourceKey,
    status: "error" as const,
    isManual,
    genreId: effectiveGenreId,
    limit: 1,
    offset: 0,
  }
  const { data: errorCountData } = useQuery({
    queryKey: queryKeys.novels(errorCountParams),
    queryFn: () => crawlApi.listNovels(errorCountParams),
  })
  const errorTotal = errorCountData?.total ?? 0

  const retryMutation = useMutation({
    mutationFn: (id: number) => crawlApi.retryNovel(id),
    onSuccess: () => {
      toast.message(t("site.toastRecrawl"))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const forceMutation = useMutation({
    mutationFn: (id: number) => crawlApi.forceAcceptNovel(id),
    onSuccess: (result) => {
      if (!result.success) {
        toast.error(result.error ?? t("lifecycle.error"))
        return
      }
      toast.message(t("site.toastForce"))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const deleteNovelMutation = useMutation({
    mutationFn: (id: number) => crawlApi.deleteNovel(id),
    onSuccess: () => {
      setConfirmDeleteId(null)
      toast.success(t("site.deleteOk"))
      setSelectedIds(new Set())
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const retryAllErrorsMutation = useMutation({
    mutationFn: () =>
      crawlApi.retryErrorNovels({
        sourceKey,
        isManual,
        genreId: effectiveGenreId,
        limit: 100,
      }),
    onSuccess: (result) => {
      setSelectedIds(new Set())
      if (result.queued > 0) {
        toast.message(t("site.toastRetryQueued", { count: result.queued }))
      } else {
        toast.message(t("site.toastRetryNone"))
      }
      if (result.skipped > 0) toast.error(t("site.toastSkipped", { count: result.skipped }))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const bulkRecrawlMutation = useMutation({
    mutationFn: async (items: Novel[]) => {
      let ok = 0
      let fail = 0
      // Chỉ nhận novel error/fully_crawled (khớp canRecrawl() lọc checkbox
      // ở trên) — rejected dùng nút "Buộc nhận" riêng từng dòng, KHÔNG qua
      // action hàng loạt này (sửa 17/9/2026: bỏ nhánh "rejected" chết —
      // checkbox đã lọc từ trước nên nhánh này không bao giờ chạy tới,
      // để lại dễ hiểu lầm là có hỗ trợ buộc-nhận hàng loạt).
      for (const novel of items) {
        try {
          await crawlApi.retryNovel(novel.id)
          ok += 1
        } catch {
          fail += 1
        }
      }
      return { ok, fail }
    },
    onSuccess: ({ ok, fail }) => {
      setSelectedIds(new Set())
      if (ok > 0) toast.message(t("site.toastRecrawlBatch", { count: ok }))
      if (fail > 0) toast.error(t("site.toastRecrawlFail", { count: fail }))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const bulkExportMutation = useMutation({
    mutationFn: (ids: number[]) => crawlApi.exportNovelsBatch(ids, "bundle"),
    onSuccess: () => {
      toast.success(t("site.exportBatchOk"))
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const rowBusy =
    bulkRecrawlMutation.isPending ||
    bulkExportMutation.isPending ||
    retryAllErrorsMutation.isPending ||
    (retryMutation.isPending
      ? retryMutation.variables
      : forceMutation.isPending
        ? forceMutation.variables
        : null)

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)

  function toggleOne(id: number, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  function toggleAllOnPage(checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      for (const n of selectableOnPage) {
        if (checked) next.add(n.id)
        else next.delete(n.id)
      }
      return next
    })
  }

  return (
    <div className="space-y-3">
      <Toolbar>
        {isManual !== true && (genresData?.items.length ?? 0) > 0 && (
          <Select
            value={genreFilter === "all" ? GENRE_FILTER_ALL : String(genreFilter)}
            onValueChange={(v) => {
              if (!v) return
              onGenreFilterChange(v === GENRE_FILTER_ALL ? "all" : Number(v))
            }}
          >
            <SelectTrigger className="h-10 w-52">
              <SelectValue>
                {(v: string) =>
                  v === GENRE_FILTER_ALL
                    ? t("site.allGenres")
                    : (genreById.get(Number(v))?.label ?? v)
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={GENRE_FILTER_ALL}>{t("site.allGenres")}</SelectItem>
              {(genresData?.items ?? []).map((g) => (
                <SelectItem key={g.id} value={String(g.id)}>
                  {g.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Select
          value={status}
          onValueChange={(v) => {
            if (!v) return
            onStatusChange(v as LifecycleStatus | "all")
          }}
        >
          <SelectTrigger className="h-10 w-52">
            <SelectValue>
              {(v: string) => statusOptions.find((o) => o.value === v)?.label ?? v}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="search"
          placeholder={t("site.searchNovels")}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-10 min-w-[14rem] flex-1 sm:max-w-xs"
        />
        {errorTotal > 0 && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => retryAllErrorsMutation.mutate()}
            disabled={retryAllErrorsMutation.isPending || bulkRecrawlMutation.isPending}
          >
            {retryAllErrorsMutation.isPending
              ? t("site.queueing")
              : t("site.retryAllErrors", { count: errorTotal })}
          </Button>
        )}
        {selectedRetryable.length > 0 && (
          <Button
            size="sm"
            onClick={() => bulkRecrawlMutation.mutate(selectedRetryable)}
            disabled={bulkRecrawlMutation.isPending || retryAllErrorsMutation.isPending || bulkExportMutation.isPending}
          >
            {bulkRecrawlMutation.isPending
              ? t("site.sending")
              : t("site.recrawlSelected", { count: selectedRetryable.length })}
          </Button>
        )}
        {selectedExportable.length > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              bulkExportMutation.mutate(selectedExportable.map((n) => n.id))
            }
            disabled={bulkExportMutation.isPending || bulkRecrawlMutation.isPending}
          >
            {bulkExportMutation.isPending
              ? t("novel.exporting")
              : t("site.exportSelected", { count: selectedExportable.length })}
          </Button>
        )}
        {isFetching && <span className="text-xs text-muted-foreground">{t("app.loading")}</span>}
      </Toolbar>

      {error && (
        <p className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : t("app.unknownError")}
        </p>
      )}

      {novels !== null && total === 0 && !error && (
        <Alert>
          <AlertDescription>{t("site.emptyNovels")}</AlertDescription>
        </Alert>
      )}

      {novels !== null && total > 0 && (
        <Card className="overflow-hidden py-0">
          <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
            <p className="text-sm font-medium">
              {isManual === true
                ? t("site.novelsManual")
                : isManual === false
                  ? t("site.novelsScanned")
                  : t("site.novelsAll")}
            </p>
            <p className="shrink-0 text-xs text-muted-foreground">
              {t("common.range", { from, to, total })}
            </p>
          </div>
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10 px-2">
                  <Checkbox
                    checked={allSelectableSelected}
                    indeterminate={someSelectableSelected}
                    disabled={
                      selectableOnPage.length === 0 ||
                      bulkRecrawlMutation.isPending ||
                      retryAllErrorsMutation.isPending
                    }
                    onCheckedChange={(checked) => toggleAllOnPage(checked === true)}
                    aria-label={t("site.selectAllPage")}
                  />
                </TableHead>
                <TableHead className="w-12 px-1 text-center tabular-nums">#</TableHead>
                <TableHead>{t("site.colTitle")}</TableHead>
                {isManual !== true && <TableHead>{t("site.colGenre")}</TableHead>}
                <TableHead>{t("site.colStatus")}</TableHead>
                <TableHead>{t("site.colProgress")}</TableHead>
                <TableHead className="text-right">{t("site.colActions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {novels.map((novel, index) => {
                const selectable = canSelectNovel(novel)
                const checked = selectedIds.has(novel.id)
                const stt = offset + index + 1
                return (
                  <TableRow key={novel.id} data-state={checked ? "selected" : undefined}>
                    <TableCell className="px-2">
                      <Checkbox
                        checked={checked}
                        disabled={
                          !selectable ||
                          bulkRecrawlMutation.isPending ||
                          retryAllErrorsMutation.isPending
                        }
                        onCheckedChange={(v) => toggleOne(novel.id, v === true)}
                        aria-label={t("site.selectNovel", { stt })}
                      />
                    </TableCell>
                    <TableCell className="px-1 text-center tabular-nums text-muted-foreground">
                      {stt}
                    </TableCell>
                    <TableCell className="min-w-0 max-w-0 whitespace-normal">
                      <Link
                        to={`/novels/${novel.id}`}
                        className="block truncate font-medium hover:underline"
                        title={novel.title}
                      >
                        {novel.title}
                      </Link>
                      {novel.error_message && (
                        <p className="truncate text-xs text-destructive" title={novel.error_message}>
                          {novel.error_message}
                        </p>
                      )}
                    </TableCell>
                    {isManual !== true && (
                      <TableCell className="text-xs text-muted-foreground">
                        {novel.genre_id != null
                          ? (genreById.get(novel.genre_id)?.label ?? `#${novel.genre_id}`)
                          : "—"}
                      </TableCell>
                    )}
                    <TableCell className="whitespace-normal">
                      <StatusBadge status={novel.lifecycle_status} />
                    </TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">
                      {novel.last_chapter_index > 0 || novel.total_chapters
                        ? `${novel.last_chapter_index}/${novel.total_chapters ?? "?"}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right whitespace-normal">
                      <div className="inline-flex flex-wrap items-center justify-end gap-1">
                        {novel.lifecycle_status === "error" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => retryMutation.mutate(novel.id)}
                            disabled={
                              rowBusy === novel.id ||
                              bulkRecrawlMutation.isPending ||
                              retryAllErrorsMutation.isPending
                            }
                          >
                            {rowBusy === novel.id ? t("site.retrying") : t("site.retry")}
                          </Button>
                        )}
                        {novel.lifecycle_status === "fully_crawled" && (
                          <Link
                            to={`/novels/${novel.id}`}
                            className={buttonVariants({ variant: "outline", size: "sm" })}
                          >
                            {t("site.openNovel")}
                          </Link>
                        )}
                        {novel.lifecycle_status === "rejected" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => forceMutation.mutate(novel.id)}
                            disabled={
                              rowBusy === novel.id ||
                              bulkRecrawlMutation.isPending ||
                              retryAllErrorsMutation.isPending
                            }
                          >
                            {rowBusy === novel.id ? t("site.processing") : t("site.forceAccept")}
                          </Button>
                        )}
                        {novel.lifecycle_status === "crawling" && (
                          <span className="text-xs text-muted-foreground">{t("site.crawling")}</span>
                        )}
                        {novel.lifecycle_status !== "crawling" && (
                          <ActionMenu
                            label="⋯"
                            size="sm"
                            variant="ghost"
                            align="end"
                            showChevron={false}
                            disabled={
                              deleteNovelMutation.isPending ||
                              rowBusy === novel.id ||
                              bulkRecrawlMutation.isPending ||
                              retryAllErrorsMutation.isPending
                            }
                          >
                            {novel.lifecycle_status === "fully_crawled" ? (
                              <ActionMenuItem
                                disabled={rowBusy === novel.id}
                                onSelect={() => retryMutation.mutate(novel.id)}
                              >
                                {rowBusy === novel.id ? t("site.syncing") : t("site.sync")}
                              </ActionMenuItem>
                            ) : null}
                            <ActionMenuItem
                              destructive
                              disabled={deleteNovelMutation.isPending || rowBusy === novel.id}
                              onSelect={() => setConfirmDeleteId(novel.id)}
                            >
                              {t("site.delete")}
                            </ActionMenuItem>
                          </ActionMenu>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          </div>
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-end gap-2 border-t px-4 py-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                disabled={offset === 0}
              >
                {t("common.prevArrow")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                disabled={offset + PAGE_SIZE >= total}
              >
                {t("common.nextArrow")}
              </Button>
            </div>
          )}
        </Card>
      )}

      <ConfirmDialog
        open={confirmDeleteId != null}
        onOpenChange={(open) => !open && setConfirmDeleteId(null)}
        title={t("common.deleteTitle")}
        description={t("site.deleteConfirm")}
        confirmLabel={t("site.delete")}
        confirming={deleteNovelMutation.isPending}
        onConfirm={() => {
          if (confirmDeleteId != null) deleteNovelMutation.mutate(confirmDeleteId)
        }}
      />
    </div>
  )
}
