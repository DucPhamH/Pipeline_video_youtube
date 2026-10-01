import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import {
  AlertTriangle,
  BookOpen,
  Check,
  FileText,
  Headphones,
  LayoutPanelLeft,
  Lock,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Shirt,
  Trash2,
} from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { PageHeader, PageShell, SectionCard, SegmentedTabs } from "@/components/PageChrome"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { BookCover } from "@/components/BookCover"
import { EmptyState } from "@/components/EmptyState"
import { StatusPill } from "@/components/StatusPill"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { ApiError } from "@/api/client"
import { ttsApi } from "@/features/tts/api"
import { translateApi } from "../api"
import { StartTranslationModal } from "../components/StartTranslationModal"
import { NamesTab } from "../components/NamesTab"
import { modeVisual, useModeBlurb, useModeTitle, useParamsSummary } from "../components/variantVisual"
import {
  jobCanDelete,
  jobCanResume,
  jobIsActive,
  retranslateDeletes,
  useJobActions,
} from "../hooks/useJobActions"
import { useStatusLabels } from "../hooks/useStatusLabels"
import { useConfirm } from "@/components/useConfirm"
import type { GlossaryTerm, Job, StyleProfile, Variant, Work } from "../types"
import { PageSkeleton } from "@/components/Skeleton"

type Tab = "translate" | "glossary" | "names" | "source"
const TABS: Tab[] = ["translate", "glossary", "names", "source"]

const POLL_MS = 1500
/** Số tick poll thêm sau khi job full xong, chờ backend auto-chain variant con. */
const CHAIN_GRACE_TICKS = 20

/** Ô "Tạo nhanh" — mở modal với mode chọn sẵn. */
const QUICK_MODES = ["pov", "style_clone", "audio_cut", "reskin"] as const

function autoModalSeenKey(workId: number) {
  return `translate.autoModalSeen.v1.${workId}`
}

type StepState = "done" | "live" | "warn" | "todo" | "unknown"
type PipelineStep = {
  key: string
  label: string
  detail: ReactNode
  state: StepState
  stage: "collect" | "translate" | "listen"
  progress?: number | null
}

const STAGE_BG = { collect: "bg-stage-collect", translate: "bg-stage-translate", listen: "bg-stage-listen" } as const
const STAGE_BORDER = {
  collect: "border-stage-collect",
  translate: "border-stage-translate",
  listen: "border-stage-listen",
} as const

function PipelineStepper({ steps, label }: { steps: PipelineStep[]; label: string }) {
  return (
    <ol
      aria-label={label}
      className="grid grid-cols-2 gap-x-5 gap-y-4 rounded-[16px] border border-border bg-card px-5 py-4 sm:grid-cols-3 lg:grid-cols-5"
    >
      {steps.map((s) => {
        const filled = s.state === "done"
        return (
          <li key={s.key} className="min-w-0 space-y-2">
            {s.state === "live" ? (
              <Progress value={s.progress} tone={s.stage} live size="md" className="h-1.5" />
            ) : (
              <div
                className={cn(
                  "h-1.5 rounded-full",
                  filled ? STAGE_BG[s.stage] : s.state === "warn" ? "bg-warning" : "bg-track",
                )}
              />
            )}
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-[22px] shrink-0 items-center justify-center rounded-full border-[1.5px]",
                  filled && cn(STAGE_BG[s.stage], STAGE_BORDER[s.stage], "text-white"),
                  s.state === "live" && cn(STAGE_BORDER[s.stage], "bg-card"),
                  s.state === "warn" && "border-warning bg-warning-soft text-warning",
                  s.state === "todo" && "border-input bg-card",
                  s.state === "unknown" && "border-dashed border-input bg-card",
                )}
                aria-hidden
              >
                {filled ? <Check className="size-3" strokeWidth={3} /> : null}
                {s.state === "live" ? <span className={cn("dot-live size-2 rounded-full", STAGE_BG[s.stage])} /> : null}
                {s.state === "warn" ? <AlertTriangle className="size-3" /> : null}
              </span>
              <span className="truncate text-sm font-semibold">{s.label}</span>
            </div>
            <div className="truncate pl-[30px] text-[13px] text-muted-foreground">{s.detail}</div>
          </li>
        )
      })}
    </ol>
  )
}

export function TranslateWorkPage() {
  const t = useT()
  const navigate = useNavigate()
  const { workId } = useParams<{ workId: string }>()
  const id = Number(workId)
  const actions = useJobActions()
  const modeTitle = useModeTitle()
  const modeBlurb = useModeBlurb()
  const { jobStatusLabel } = useStatusLabels()
  const [confirm, confirmDialog] = useConfirm()

  const [work, setWork] = useState<Work | null>(null)
  const [jobsByVariant, setJobsByVariant] = useState<Record<number, Job | null>>({})
  const [glossary, setGlossary] = useState<GlossaryTerm[]>([])
  const [profiles, setProfiles] = useState<StyleProfile[]>([])
  const paramsSummary = useParamsSummary(profiles)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  /** variant id → tts work id (đã gửi sang Nghe). null = không đọc được tts-service. */
  const [ttsByVariant, setTtsByVariant] = useState<Record<number, number> | null>({})
  // Tab + variant skin map nằm trên URL (?tab=names&skin=12) để modal/variant
  // row link thẳng tới bảng tên / bảng đổi vỏ.
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get("tab") as Tab | null
  const tab: Tab = tabParam && TABS.includes(tabParam) ? tabParam : "translate"
  const skinParam = Number(searchParams.get("skin"))
  const skinVariantId = Number.isFinite(skinParam) && skinParam > 0 ? skinParam : null
  const setTab = useCallback(
    (next: Tab, extra?: Record<string, string>) => {
      setSearchParams(
        (cur) => {
          const p = new URLSearchParams(cur)
          if (next === "translate") p.delete("tab")
          else p.set("tab", next)
          if (next !== "names") p.delete("skin")
          for (const [k, v] of Object.entries(extra ?? {})) p.set(k, v)
          return p
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )
  const [candidateCount, setCandidateCount] = useState<number | null>(null)

  const [srcTerm, setSrcTerm] = useState("")
  const [tgtTerm, setTgtTerm] = useState("")
  const [protectedTerm, setProtectedTerm] = useState(true)

  const [modalOpen, setModalOpen] = useState(false)
  const [modalVariantId, setModalVariantId] = useState<number | null>(null)
  const [modalMode, setModalMode] = useState<string | null>(null)

  const fetchJobs = useCallback(async (w: Work) => {
    const entries = await Promise.all(
      w.variants.map(async (v) => {
        if (!v.latest_job_id) return [v.id, null] as const
        try {
          return [v.id, await translateApi.getJob(v.latest_job_id)] as const
        } catch {
          return [v.id, null] as const
        }
      }),
    )
    return Object.fromEntries(entries) as Record<number, Job | null>
  }, [])

  const loadWork = useCallback(async () => {
    if (!Number.isFinite(id)) return
    try {
      const w = await translateApi.getWork(id)
      setWork(w)
      setGlossary(await translateApi.listGlossary(id))
      setJobsByVariant(await fetchJobs(w))

      const neverStarted = w.variants.every((v) => v.latest_job_id == null)
      if (neverStarted) {
        let seen = false
        try {
          seen = localStorage.getItem(autoModalSeenKey(id)) === "1"
        } catch {
          /* ignore */
        }
        if (!seen) {
          setModalVariantId(w.variants[0]?.id ?? null)
          setModalMode(null)
          setModalOpen(true)
          try {
            localStorage.setItem(autoModalSeenKey(id), "1")
          } catch {
            /* ignore quota */
          }
        }
      }
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }, [id, t, fetchJobs])

  useEffect(() => {
    void loadWork()
    translateApi.listStyleProfiles().then(setProfiles).catch(() => setProfiles([]))
    translateApi
      .listNames(id)
      .then((list) => setCandidateCount(list.filter((n) => n.status === "candidate").length))
      .catch(() => setCandidateCount(null))
    // initial load only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // Bước "Audio": tìm work TTS đã nhận handoff từ variant của work này
  // (external_id = translate:variant:{id}). Lỗi tts-service → để trạng thái "không rõ".
  const workTitle = work?.title
  useEffect(() => {
    if (!workTitle) return
    let cancelled = false
    ttsApi
      .listWorks()
      .then(async (r) => {
        const candidates = r.items.filter((x) => x.source_type === "translate_handoff" && x.title === workTitle)
        const details = await Promise.all(candidates.map((c) => ttsApi.getWork(c.id).catch(() => null)))
        const map: Record<number, number> = {}
        for (const d of details) {
          const m = /^translate:variant:(\d+)$/.exec(d?.external_id ?? "")
          if (d && m) map[Number(m[1])] = d.id
        }
        if (!cancelled) setTtsByVariant(map)
      })
      .catch(() => {
        if (!cancelled) setTtsByVariant(null)
      })
    return () => {
      cancelled = true
    }
  }, [workTitle])

  // Tab Tên sửa cùng bảng glossary — quay lại tab Thuật ngữ thì tải lại.
  useEffect(() => {
    if (tab !== "glossary" || !Number.isFinite(id)) return
    translateApi.listGlossary(id).then(setGlossary).catch(() => undefined)
  }, [tab, id])

  // Variant con (fork từ full) chưa có job, đợi job full xong để backend auto-chain.
  const [graceTicks, setGraceTicks] = useState(0)
  const anyJobActive = Object.values(jobsByVariant).some((j) => jobIsActive(j))
  const anyWaitingChain =
    work?.variants.some((v) => {
      if (v.latest_job_id != null || v.source_variant_id == null) return false
      const srcJob = jobsByVariant[v.source_variant_id]
      return srcJob != null && (jobIsActive(srcJob) || srcJob.status === "completed")
    }) ?? false
  const shouldPoll = anyJobActive || (anyWaitingChain && graceTicks < CHAIN_GRACE_TICKS)

  // Poll cả work (status variant, latest_job_id mới do auto-chain) lẫn job;
  // setTimeout tự lên lịch để các request không chồng nhau.
  useEffect(() => {
    if (!shouldPoll || !Number.isFinite(id)) return
    let cancelled = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const w = await translateApi.getWork(id)
        const jobs = await fetchJobs(w)
        if (cancelled) return
        setWork(w)
        setJobsByVariant(jobs)
        const stillActive = Object.values(jobs).some((j) => jobIsActive(j))
        setGraceTicks((g) => (stillActive ? 0 : g + 1))
      } catch {
        /* lỗi poll tạm thời — thử lại tick sau */
      }
      if (!cancelled) timer = window.setTimeout(tick, POLL_MS)
    }
    timer = window.setTimeout(tick, POLL_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [shouldPoll, id, fetchJobs])

  function openModalFor(variantId: number | null, mode: string | null = null) {
    setModalVariantId(variantId)
    setModalMode(mode)
    setModalOpen(true)
  }

  /** Modal: "Duyệt tên trước khi dịch" → sang tab Tên (job chưa chạy). */
  function handleReviewNames() {
    setTab("names")
    toast.message(t("translate.reviewNamesStartHint"))
  }

  /** Modal: tạo variant reskin rồi sang bảng đổi vỏ trước khi chạy job. */
  function handleReviewSkinMap(variantId: number) {
    void loadWork()
    setTab("names", { skin: String(variantId) })
    toast.message(t("translate.reviewSkinMapStartHint"))
  }

  function handleStarted(_variantId: number, jobId: number) {
    setGraceTicks(0)
    void loadWork()
    navigate(`/translate/${id}/jobs/${jobId}`)
  }

  async function handlePause(variantId: number, job: Job) {
    setBusy(true)
    const j = await actions.pause(job.id)
    if (j) setJobsByVariant((m) => ({ ...m, [variantId]: j }))
    setBusy(false)
  }

  async function handleDelete(variantId: number, job: Job) {
    const confirmed = await confirm({
      title: t("common.deleteTitle"),
      description: t("translate.deleteJobConfirm"),
      confirmLabel: t("translate.deleteJob"),
    })
    if (!confirmed) return
    setBusy(true)
    const ok = await actions.remove(job.id)
    if (ok) setJobsByVariant((m) => ({ ...m, [variantId]: null }))
    setBusy(false)
  }

  async function handleRetranslate(variantId: number, job: Job) {
    if (retranslateDeletes(job)) {
      const confirmed = await confirm({
        title: t("translate.retranslateConfirmTitle"),
        description: t("translate.retranslateConfirm"),
        confirmLabel: t("translate.retranslate"),
      })
      if (!confirmed) return
    }
    setBusy(true)
    const j = await actions.retranslate(job, variantId)
    if (j) {
      setJobsByVariant((m) => ({ ...m, [variantId]: j }))
      navigate(`/translate/${id}/jobs/${j.id}`)
    }
    setBusy(false)
  }

  async function handleCloneVariant(variantId: number) {
    setBusy(true)
    try {
      await translateApi.cloneVariant(variantId)
      toast.success(t("translate.variantCloned"))
      await loadWork()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function handleAddGlossary(e?: FormEvent) {
    e?.preventDefault()
    if (!srcTerm.trim()) return
    try {
      const term = await translateApi.addGlossary(id, {
        source_term: srcTerm.trim(),
        target_term: tgtTerm.trim(),
        protected: protectedTerm,
      })
      setGlossary((g) => [...g, term].sort((a, b) => a.source_term.localeCompare(b.source_term)))
      setSrcTerm("")
      setTgtTerm("")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function handleDeleteGlossary(term: GlossaryTerm) {
    const termId = term.id
    const confirmed = await confirm({
      title: t("common.deleteTitle"),
      description: t("translate.glossaryDeleteConfirm", { term: term.source_term }),
    })
    if (!confirmed) return
    try {
      await translateApi.deleteGlossary(id, termId)
      setGlossary((g) => g.filter((x) => x.id !== termId))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  function variantCard(v: Variant) {
    const job = jobsByVariant[v.id] ?? null
    const active = jobIsActive(job)
    const vis = modeVisual(v.mode)
    const Icon = vis.icon
    const pct = job && job.total_segments > 0 ? (job.done_segments / job.total_segments) * 100 : 0
    const waitingOnFull =
      !job &&
      v.source_variant_id != null &&
      work?.variants.find((x) => x.id === v.source_variant_id)?.status !== "ready"
    const ttsWorkId = ttsByVariant?.[v.id]
    const status = job ? job.status : waitingOnFull ? "waiting" : "idle"
    const statusLabel = job
      ? jobStatusLabel(job.status)
      : waitingOnFull
        ? t("translate.waitingOnFull")
        : v.mode === "reskin"
          ? t("translate.hub.reviewMap")
          : t("translate.noJobYet")

    return (
      <li key={v.id} className="flex min-w-0 flex-col gap-3 rounded-[16px] border border-border bg-card p-[18px]">
        <div className="flex items-start gap-2.5">
          <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-[10px]", vis.tint)}>
            <Icon className="size-[18px]" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] font-semibold">
              {modeTitle(v.mode)} <span className="font-mono text-xs font-normal text-muted-foreground">#{v.id}</span>
            </p>
            <p className="truncate text-[13px] text-muted-foreground">
              {paramsSummary(v.mode, v.mode_params, job?.model) || v.lang_tgt}
            </p>
          </div>
          <StatusPill status={status} label={statusLabel} className="max-w-[45%] shrink truncate" />
        </div>

        {job ? (
          <div className="space-y-1.5">
            <Progress value={pct} tone={vis.tone} live={active} label={statusLabel} />
            <p className="flex justify-between gap-2 font-mono text-xs text-muted-foreground tabular-nums">
              <span>
                {job.done_segments}/{job.total_segments} {t("translate.chaptersShort")}
                {job.failed_segments ? ` · ${job.failed_segments} ${t("translate.failShort")}` : ""}
              </span>
              <span>{Math.round(pct)}%</span>
            </p>
          </div>
        ) : (
          <p className="text-[13px] text-muted-foreground">
            {waitingOnFull ? t("translate.waitingOnFull") : v.mode === "reskin" ? t("translate.skinMapNudge") : modeBlurb(v.mode)}
          </p>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-2">
          {job ? (
            <>
              {job.done_segments > 0 ? (
                <Link to={`/read/translate/${id}/${job.id}`} className={buttonVariants({ size: "sm" })}>
                  <BookOpen aria-hidden />
                  {t("reader.read")}
                </Link>
              ) : null}
              <Link
                to={`/translate/${id}/jobs/${job.id}`}
                className={buttonVariants({ size: "sm", variant: job.done_segments > 0 ? "outline" : "default" })}
              >
                <LayoutPanelLeft aria-hidden />
                {t("translate.hub.workspace")}
              </Link>
              {ttsWorkId != null ? (
                <Link to={`/tts/${ttsWorkId}`} className={buttonVariants({ size: "sm", variant: "secondary" })}>
                  <Headphones aria-hidden />
                  {t("translate.hub.listen")}
                </Link>
              ) : null}
              {active ? (
                <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void handlePause(v.id, job)}>
                  <Pause aria-hidden />
                  {t("translate.pauseJob")}
                </Button>
              ) : null}
            </>
          ) : (
            <Button type="button" size="sm" onClick={() => openModalFor(v.id)}>
              <Play aria-hidden />
              {t("translate.startJob")}
            </Button>
          )}
          {v.mode === "reskin" ? (
            <Button
              type="button"
              size="sm"
              variant={job ? "ghost" : "outline"}
              onClick={() => setTab("names", { skin: String(v.id) })}
            >
              <Shirt aria-hidden />
              {t("translate.skinMapOpen")}
            </Button>
          ) : null}
          <div className="ml-auto">
            <ActionMenu
              label={<MoreHorizontal className="size-4" aria-label={t("novel.moreActions")} />}
              variant="ghost"
              showChevron={false}
              disabled={busy}
            >
              {job ? (
                <ActionMenuItem
                  disabled={active || !(jobCanResume(job) || jobCanDelete(job))}
                  onSelect={() => void handleRetranslate(v.id, job)}
                >
                  {t("translate.retranslate")}
                </ActionMenuItem>
              ) : null}
              <ActionMenuItem onSelect={() => void handleCloneVariant(v.id)}>{t("translate.cloneVariant")}</ActionMenuItem>
              {job ? (
                <ActionMenuItem destructive disabled={!jobCanDelete(job)} onSelect={() => void handleDelete(v.id, job)}>
                  {t("translate.deleteJob")}
                </ActionMenuItem>
              ) : null}
            </ActionMenu>
          </div>
        </div>
      </li>
    )
  }

  if (loadError) {
    return (
      <PageShell>
        <PageHeader
          breadcrumbs={[{ label: t("translate.title"), to: "/translate" }, { label: "—" }]}
          title={t("translate.title")}
        />
        <EmptyState icon={AlertTriangle} tone="neutral" title={loadError} />
      </PageShell>
    )
  }

  if (!work) {
    return (
      <PageShell>
        <PageSkeleton />
      </PageShell>
    )
  }

  // Work handoff từ crawl mang external_id "crawl:novel:{id}" → link về truyện gốc.
  const crawlMatch = /^crawl:novel:(\d+)$/.exec(work.external_id ?? "")
  const crawlNovelId = crawlMatch ? Number(crawlMatch[1]) : null
  const fromCrawl = work.source_type === "crawl_handoff"

  // ── Pipeline: chỉ khẳng định những gì dữ liệu cho biết; còn lại để trung tính.
  const fullVariants = work.variants.filter((v) => v.mode === "full")
  const otherVariants = work.variants.filter((v) => v.mode !== "full")
  const jobOf = (v: Variant) => jobsByVariant[v.id] ?? null
  const progressOf = (vs: Variant[]) => {
    const live = vs.map(jobOf).find((j) => jobIsActive(j))
    return live && live.total_segments > 0 ? (live.done_segments / live.total_segments) * 100 : null
  }
  const fullState: StepState = fullVariants.some((v) => v.status === "ready")
    ? "done"
    : fullVariants.some((v) => jobIsActive(jobOf(v)) || v.status === "running" || v.status === "queued")
      ? "live"
      : fullVariants.some((v) => v.status === "failed")
        ? "warn"
        : "todo"
  const otherState: StepState = otherVariants.some((v) => jobIsActive(jobOf(v)) || v.status === "running")
    ? "live"
    : otherVariants.some((v) => v.status === "ready")
      ? "done"
      : otherVariants.some((v) => v.status === "failed")
        ? "warn"
        : "todo"
  const ttsCount = ttsByVariant ? Object.keys(ttsByVariant).filter((k) => work.variants.some((v) => v.id === Number(k))).length : 0
  const cleanOk = work.missing_cleaned === 0 && work.unreviewed_chapters === 0

  const steps: PipelineStep[] = [
    {
      key: "collect",
      label: t("translate.hub.stepCollected"),
      stage: "collect",
      state: work.chapters.length > 0 ? "done" : "todo",
      detail:
        crawlNovelId != null ? (
          <Link to={`/novels/${crawlNovelId}`} className="hover:text-foreground hover:underline">
            {t("translate.hub.chaptersCount", { count: work.chapters.length })}
          </Link>
        ) : (
          t("translate.hub.chaptersCount", { count: work.chapters.length })
        ),
    },
    {
      key: "clean",
      label: t("translate.hub.stepCleaned"),
      stage: "collect",
      state: !fromCrawl ? "unknown" : cleanOk ? "done" : "warn",
      detail: !fromCrawl
        ? t("translate.hub.notTracked")
        : cleanOk
          ? t("translate.hub.allReviewed")
          : [
              work.missing_cleaned > 0
                ? t("translate.qualityGateMissingCleaned", { count: String(work.missing_cleaned) })
                : null,
              work.unreviewed_chapters > 0
                ? t("translate.qualityGateUnreviewed", { count: String(work.unreviewed_chapters) })
                : null,
            ]
              .filter(Boolean)
              .join(" · "),
    },
    {
      key: "translate",
      label: t("translate.hub.stepTranslated"),
      stage: "translate",
      state: fullState,
      progress: progressOf(fullVariants),
      detail:
        fullState === "done"
          ? `${modeTitle("full")} · ${work.lang_tgt}`
          : fullState === "live"
            ? t("translate.statusRunning")
            : fullState === "warn"
              ? t("translate.statusFailed")
              : t("translate.hub.notStarted"),
    },
    {
      key: "adapt",
      label: t("translate.hub.stepAdapted"),
      stage: "translate",
      state: otherState,
      progress: progressOf(otherVariants),
      detail: otherVariants.length
        ? t("translate.hub.variantsCount", { count: otherVariants.length })
        : t("translate.hub.noneYet"),
    },
    {
      key: "audio",
      label: t("translate.hub.stepAudio"),
      stage: "listen",
      state: ttsByVariant == null ? "unknown" : ttsCount > 0 ? "done" : "todo",
      detail:
        ttsByVariant == null
          ? t("translate.hub.unknown")
          : ttsCount > 0
            ? t("translate.hub.sentToListen", { count: ttsCount })
            : t("translate.hub.notStarted"),
    },
  ]

  const sourceLabel =
    work.source_type === "upload"
      ? t("translate.sourceUpload")
      : work.source_type === "crawl_handoff"
        ? t("translate.sourceCrawl")
        : work.source_type

  return (
    <PageShell>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
        <div className="w-24 shrink-0 sm:w-32">
          <BookCover title={work.title} subtitle={`${work.lang_src} → ${work.lang_tgt}`} lift={false} />
        </div>
        <div className="min-w-0 flex-1">
          <PageHeader
            breadcrumbs={[{ label: t("translate.title"), to: "/translate" }, { label: work.title }]}
            title={work.title}
            meta={
              <>
                <span className="inline-flex h-6 items-center rounded-full bg-accent px-2.5 font-mono text-xs font-semibold text-accent-foreground">
                  {work.lang_src} → {work.lang_tgt}
                </span>
                {crawlNovelId != null ? (
                  <Link
                    to={`/novels/${crawlNovelId}`}
                    className="inline-flex h-6 items-center rounded-full bg-stage-collect-soft px-2.5 text-xs font-semibold text-stage-collect hover:underline"
                  >
                    {t("translate.backToCrawl")}
                  </Link>
                ) : (
                  <span className="inline-flex h-6 items-center rounded-full bg-stage-collect-soft px-2.5 text-xs font-semibold text-stage-collect">
                    {sourceLabel}
                  </span>
                )}
                <span className="inline-flex h-6 items-center rounded-full bg-muted px-2.5 text-xs font-semibold text-muted-foreground">
                  {t("translate.hub.chaptersCount", { count: work.chapters.length })}
                </span>
                {work.author ? <span className="text-sm">{work.author}</span> : null}
              </>
            }
            primaryAction={
              <Button type="button" onClick={() => openModalFor(null)}>
                <Plus aria-hidden />
                {t("translate.newTranslation")}
              </Button>
            }
          />
        </div>
      </div>

      <PipelineStepper steps={steps} label={t("translate.hub.pipeline")} />

      {fromCrawl && !cleanOk ? (
        <p className="flex items-start gap-2 rounded-xl bg-warning-soft px-4 py-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>{t("translate.qualityGateHint")}</span>
        </p>
      ) : null}

      <SegmentedTabs
        variant="underline"
        value={tab}
        onChange={(v) => setTab(v)}
        items={[
          { value: "translate", label: t("translate.hub.tabVersions"), count: work.variants.length },
          { value: "names", label: t("translate.namesTab"), count: candidateCount || undefined },
          { value: "glossary", label: t("translate.glossary"), count: glossary.length || undefined },
          { value: "source", label: t("translate.hub.tabSource"), count: work.chapters.length },
        ]}
      />

      {tab === "translate" ? (
        <div className="space-y-6">
          {work.variants.length === 0 ? (
            <EmptyState
              icon={BookOpen}
              tone="translate"
              title={t("translate.noJobYet")}
              hint={t("translate.startModalHint")}
              action={
                <Button type="button" onClick={() => openModalFor(null)}>
                  <Plus aria-hidden />
                  {t("translate.newTranslation")}
                </Button>
              }
            />
          ) : (
            <ul className="stagger grid gap-4 md:grid-cols-2 xl:grid-cols-3">{work.variants.map(variantCard)}</ul>
          )}

          <section aria-labelledby="quick-create" className="space-y-3">
            <h2 id="quick-create" className="text-[17px] font-semibold">
              {t("translate.hub.quickCreate")}
            </h2>
            <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-4">
              {QUICK_MODES.map((m) => {
                const vis = modeVisual(m)
                const Icon = vis.icon
                return (
                  <button
                    key={m}
                    type="button"
                    onClick={() => openModalFor(null, m)}
                    className="lift flex items-center gap-3 rounded-[14px] border border-border bg-card p-3.5 text-left focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                  >
                    <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-[10px]", vis.tint)}>
                      <Icon className="size-5" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold">{modeTitle(m)}</span>
                      <span className="block truncate text-[13px] text-muted-foreground">{modeBlurb(m)}</span>
                    </span>
                  </button>
                )
              })}
            </div>
          </section>
        </div>
      ) : null}

      {tab === "glossary" ? (
        <SectionCard title={t("translate.glossary")} description={t("translate.glossaryHint")}>
          <form
            className="mb-4 grid gap-3 rounded-xl bg-muted/50 p-3 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end"
            onSubmit={(e) => void handleAddGlossary(e)}
          >
            <div className="space-y-1.5">
              <Label htmlFor="g-src">{t("translate.termSrc")}</Label>
              <Input id="g-src" value={srcTerm} onChange={(e) => setSrcTerm(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="g-tgt">{t("translate.termTgt")}</Label>
              <Input id="g-tgt" value={tgtTerm} onChange={(e) => setTgtTerm(e.target.value)} />
            </div>
            <label className="flex h-9 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={protectedTerm}
                onChange={(e) => setProtectedTerm(e.target.checked)}
              />
              {t("translate.termProtected")}
            </label>
            <Button type="submit" disabled={!srcTerm.trim()}>
              <Plus aria-hidden />
              {t("translate.addTerm")}
            </Button>
          </form>
          {glossary.length === 0 ? (
            <EmptyState icon={FileText} tone="translate" compact title={t("translate.glossaryEmpty")} />
          ) : (
            <div className="max-h-[60vh] overflow-auto rounded-xl border border-border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-muted text-left text-xs font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                  <tr>
                    <th className="px-3 py-2">{t("translate.termSrc")}</th>
                    <th className="px-3 py-2">{t("translate.termTgt")}</th>
                    <th className="w-12 px-3 py-2">
                      <span className="sr-only">{t("common.confirmDelete")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {glossary.map((g) => (
                    <tr key={g.id} className="transition-colors hover:bg-muted/50">
                      <td className="px-3 py-2 font-medium">
                        <span className="inline-flex items-center gap-1.5">
                          {g.source_term}
                          {g.protected ? (
                            <Lock className="size-3.5 text-muted-foreground" aria-label={t("translate.termProtected")} />
                          ) : null}
                        </span>
                      </td>
                      <td className="px-3 py-2">{g.target_term || "—"}</td>
                      <td className="px-2 py-1 text-right">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t("common.confirmDelete")}
                          onClick={() => void handleDeleteGlossary(g)}
                        >
                          <Trash2 className="text-muted-foreground" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      ) : null}

      {tab === "names" ? (
        <NamesTab
          work={work}
          skinVariantId={skinVariantId}
          onSkinVariantChange={(vid) => setTab("names", vid != null ? { skin: String(vid) } : undefined)}
          onCandidatesCount={setCandidateCount}
        />
      ) : null}

      {tab === "source" ? (
        <SectionCard title={t("translate.chapters")}>
          {work.chapters.length === 0 ? (
            <EmptyState icon={FileText} tone="neutral" compact title={t("translate.hub.noChapters")} />
          ) : (
            <ul className="stagger -mx-2 max-h-[70vh] divide-y divide-border overflow-y-auto">
              {work.chapters.map((c) => (
                <li key={c.id} className="flex gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-muted/50">
                  <span className="w-10 shrink-0 pt-px text-right font-mono text-xs text-muted-foreground tabular-nums">
                    {c.index}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{c.title || "—"}</p>
                    <p className="mt-0.5 line-clamp-2 text-[13px] text-muted-foreground">{c.text_preview}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      ) : null}

      <StartTranslationModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        work={work}
        existingVariantId={modalVariantId}
        initialMode={modalMode}
        styleProfiles={profiles}
        onStarted={handleStarted}
        onReviewNames={handleReviewNames}
        onReviewSkinMap={handleReviewSkinMap}
      />
      {confirmDialog}
    </PageShell>
  )
}
