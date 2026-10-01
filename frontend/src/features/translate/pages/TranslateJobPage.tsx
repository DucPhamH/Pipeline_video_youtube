import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"
import { Cpu, Download, Headphones, MoreHorizontal, Pause, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { PageHeader, PageShell } from "@/components/PageChrome"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { translateApi } from "../api"
import { ttsApi } from "@/features/tts/api"
import { jobCanDelete, jobCanResume, jobIsActive, useJobActions } from "../hooks/useJobActions"
import { useJobPoll } from "../hooks/useJobPoll"
import { useModeLabel } from "../components/ModeParamsFields"
import { useConfirm } from "@/components/useConfirm"
import { getCatalogEntry } from "../providerProfiles"
import { friendlyError, qaFlagLabel } from "../errorText"
import type { AiProvider, Job, Segment, SegmentDetail, Variant, Work } from "../types"
import { PageSkeleton } from "@/components/Skeleton"
import { JobStatusStrip } from "../job/JobStatusStrip"
import { SegmentList } from "../job/SegmentList"
import { ReviewPane } from "../job/ReviewPane"
import { SwitchAiDialog } from "../job/SwitchAiDialog"
import { countByFilter, segmentMatches, type SegFilter } from "../job/segmentFilter"

const QUOTA_ERROR_RE = /429|quota|rate.?limit|insufficient/i
/** Số lần poll lỗi liên tiếp trước khi hiện "mất kết nối". */
const POLL_FAIL_WARN = 3
/** Số request getSegment song song khi gom chương gửi sang TTS. */
const TTS_FETCH_CONCURRENCY = 5

/** map async với giới hạn số request song song, giữ nguyên thứ tự kết quả. */
async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(items.length)
  let next = 0
  async function worker() {
    while (next < items.length) {
      const i = next++
      out[i] = await fn(items[i])
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
  return out
}

/** Đang gõ trong ô nhập → bỏ qua phím tắt điều hướng. */
function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  if (el.isContentEditable) return true
  const tag = el.tagName
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
}

export function TranslateJobPage() {
  const t = useT()
  const navigate = useNavigate()
  const { workId, jobId } = useParams<{ workId: string; jobId: string }>()
  const wId = Number(workId)
  const jId = Number(jobId)
  const actions = useJobActions()
  const modeLabel = useModeLabel()
  const [confirm, confirmDialog] = useConfirm()

  const [work, setWork] = useState<Work | null>(null)
  const [variant, setVariant] = useState<Variant | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [segments, setSegments] = useState<Segment[]>([])
  const [activeSeg, setActiveSeg] = useState<SegmentDetail | null>(null)
  const [editOut, setEditOut] = useState("")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState<string | null>(null)
  /** Tăng mỗi khi job được set từ nguồn khác (action/poll) — response poll cũ hơn bị bỏ. */
  const jobSeqRef = useRef(0)
  const openSegSeqRef = useRef(0)

  const [providers, setProviders] = useState<AiProvider[]>([])
  const [switchAiId, setSwitchAiId] = useState<number | null>(null)
  const [switchModel, setSwitchModel] = useState("")
  const [switchOpen, setSwitchOpen] = useState(false)

  const [segFilter, setSegFilter] = useState<SegFilter>("all")
  const [segSearch, setSegSearch] = useState("")
  /** Lọc "Cờ QA" theo 1 cờ cụ thể ("" = mọi cờ). */
  const [qaFlag, setQaFlag] = useState("")

  const applyJob = useCallback((j: Job) => {
    jobSeqRef.current += 1
    setJob(j)
  }, [])

  const load = useCallback(async () => {
    try {
      const [w, j] = await Promise.all([translateApi.getWork(wId), translateApi.getJob(jId)])
      setWork(w)
      setVariant(w.variants.find((v) => v.id === j.variant_id) ?? null)
      setJob(j)
      setSegments(await translateApi.listSegments(j.id))
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }, [wId, jId, t])

  useEffect(() => {
    void load()
    translateApi.listAiProviders().then(setProviders).catch(() => setProviders([]))
    // initial load only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wId, jId])

  const onPollData = useCallback((j: Job, segs: Segment[]) => {
    setJob(j)
    setSegments(segs)
  }, [])
  const active = jobIsActive(job)
  const pollFailures = useJobPoll({ jobId: job?.id, active, seqRef: jobSeqRef, onData: onPollData })

  const lastToastRef = useRef<{ id: number; status: string }>({ id: 0, status: "" })
  useEffect(() => {
    if (!job) return
    const prev = lastToastRef.current
    if (prev.id === job.id && prev.status === job.status) return
    const prevStatus = prev.id === job.id ? prev.status : ""
    lastToastRef.current = { id: job.id, status: job.status }
    if (!prevStatus || prevStatus === job.status) return
    if (job.status === "completed") toast.success(t("translate.jobDone"))
    else if (job.status === "failed") toast.error(friendlyError(job.error, t) || t("translate.jobFailed"))
    else if (job.status === "cancelled") toast.message(t("translate.jobStopped"))
    else if (job.status === "running") toast.message(t("translate.jobRunning"))
  }, [job, t])

  /** Mọi cờ QA đang có trong danh sách segment (để dựng bộ lọc). */
  const qaFlagsPresent = useMemo(() => {
    const set = new Set<string>()
    for (const s of segments) for (const f of s.qa_flags ?? []) set.add(f)
    return [...set].sort()
  }, [segments])

  const counts = useMemo(() => countByFilter(segments), [segments])

  const chapterTitles = useMemo(() => {
    const m = new Map<number, string>()
    for (const c of work?.chapters ?? []) if (c.title) m.set(c.index, c.title)
    return m
  }, [work])
  const titleFor = useCallback(
    (index: number) => chapterTitles.get(index) || t("translate.chapterTitleFallback", { index }),
    [chapterTitles, t],
  )

  const filteredSegments = useMemo(() => {
    const q = segSearch.trim().toLowerCase()
    return segments.filter((s) => {
      if (!segmentMatches(s, segFilter, qaFlag)) return false
      if (q) {
        const flags = (s.qa_flags ?? []).map((f) => qaFlagLabel(f, t)).join(" ")
        const blob =
          `#${s.chapter_index} ${chapterTitles.get(s.chapter_index) ?? ""} ${s.status} ${flags} ${s.output_preview} ${s.error ?? ""}`.toLowerCase()
        if (!blob.includes(q)) return false
      }
      return true
    })
  }, [segments, segFilter, segSearch, qaFlag, chapterTitles, t])

  const canResume = jobCanResume(job)
  const canDelete = jobCanDelete(job)
  const looksLikeQuotaError = Boolean(job?.error && QUOTA_ERROR_RE.test(job.error))
  const flaggedCount = job?.flagged_segments ?? counts.flagged
  const canExport = job?.status === "completed" || variant?.status === "ready"

  async function handlePause() {
    if (!job) return
    setBusy(true)
    try {
      const j = await actions.pause(job.id)
      if (j) {
        applyJob(j)
        setSegments(await translateApi.listSegments(j.id))
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  const jobModelId = job?.id
  const jobModel = job?.model
  useEffect(() => {
    if (jobModelId == null) return
    setSwitchModel(jobModel || "")
  }, [jobModelId, jobModel])

  const switchTarget =
    switchAiId != null
      ? providers.find((p) => p.id === switchAiId)
      : providers.find((p) => p.id === job?.ai_provider_id) ?? null
  const switchModelOptions = (() => {
    const kind = switchTarget?.kind
    const suggestions = (kind ? getCatalogEntry(kind)?.model_suggestions : null) ?? []
    const cur = switchModel || switchTarget?.model || job?.model || ""
    const out = [...suggestions]
    if (cur && !out.includes(cur)) out.unshift(cur)
    if (switchTarget?.model && !out.includes(switchTarget.model)) out.unshift(switchTarget.model)
    return out
  })()

  async function handleResume() {
    if (!job) return
    setBusy(true)
    const modelChanged = !!(switchModel.trim() && switchModel.trim() !== job.model)
    const cfg =
      switchAiId != null || modelChanged
        ? {
            // Giữ link registry khi chỉ đổi model — resume sau vẫn refresh key
            ai_provider_id: switchAiId ?? job.ai_provider_id ?? undefined,
            ...(switchModel.trim() ? { model: switchModel.trim() } : {}),
          }
        : undefined
    const j = await actions.resume(job.id, cfg)
    if (j) {
      applyJob(j)
      setSwitchOpen(false)
    }
    setBusy(false)
  }

  async function handleApplyAiMidRun() {
    if (!job) return
    const model = switchModel.trim()
    if (switchAiId == null && (!model || model === job.model)) return
    setBusy(true)
    const j = await actions.applyProvider(job.id, {
      ai_provider_id: switchAiId ?? job.ai_provider_id ?? undefined,
      ...(model ? { model } : {}),
    })
    if (j) {
      applyJob(j)
      setSwitchOpen(false)
    }
    setBusy(false)
  }

  async function handleDelete() {
    if (!job) return
    const confirmed = await confirm({
      title: t("common.deleteTitle"),
      description: t("translate.deleteJobConfirm"),
      confirmLabel: t("translate.deleteJob"),
    })
    if (!confirmed) return
    setBusy(true)
    try {
      const ok = await actions.remove(job.id)
      if (ok) navigate(`/translate/${wId}`)
    } finally {
      setBusy(false)
    }
  }

  /** `flagOverride` = undefined → dùng bộ lọc cờ hiện tại (nếu đang lọc "Cờ QA"). */
  async function handleRetranslateFlagged(flagOverride?: string) {
    if (!job) return
    const flag = flagOverride ?? (segFilter === "flagged" ? qaFlag : "")
    const confirmed = await confirm({
      title: t("translate.retranslateFlaggedTitle"),
      description: flag
        ? t("translate.retranslateFlaggedConfirmOne", { flag: qaFlagLabel(flag, t) })
        : t("translate.retranslateFlaggedConfirm", { count: flaggedCount }),
      confirmLabel: t("translate.retranslateFlagged"),
      destructive: false,
    })
    if (!confirmed) return
    setBusy(true)
    try {
      const j = await translateApi.retranslateFlagged(job.id, flag || undefined)
      applyJob(j)
      setSegments(await translateApi.listSegments(j.id))
      toast.success(t("translate.jobResumed"))
    } catch (err) {
      toast.error(err instanceof ApiError ? friendlyError(err.message, t) : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  /** Chặn bấm export 2 lần khi file đang tải. */
  async function runExport(kind: string, fn: (variantId: number) => Promise<void>) {
    if (!variant || exporting) return
    setExporting(kind)
    try {
      await fn(variant.id)
      toast.success(t("translate.exportOk"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setExporting(null)
    }
  }

  async function handleSendTts() {
    if (!work || !variant || !job) return
    setBusy(true)
    try {
      const details = await mapLimit(segments, TTS_FETCH_CONCURRENCY, (s) => translateApi.getSegment(s.id))
      const chapters = details
        .filter((d) => (d.output_text || "").trim())
        .map((d) => ({
          index: d.chapter_index,
          title: titleFor(d.chapter_index),
          text: d.output_text || "",
        }))
      if (chapters.length === 0) {
        toast.error(t("tts.needChapters"))
        return
      }
      const created = await ttsApi.fromTranslate({
        title: work.title,
        author: work.author,
        lang: variant.lang_tgt,
        external_id: `translate:variant:${variant.id}`,
        chapters,
      })
      toast.success(created.created ? t("tts.sent") : t("tts.alreadyThere"))
      navigate(`/tts/${created.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  const reviewDirty = activeSeg != null && editOut !== (activeSeg.output_text ?? "")

  /** true = được phép rời bản đang sửa (không có thay đổi, hoặc user đồng ý bỏ). */
  async function confirmDiscardEdits(): Promise<boolean> {
    if (!reviewDirty) return true
    return confirm({
      title: t("translate.discardEditsTitle"),
      description: t("translate.discardEditsConfirm"),
      confirmLabel: t("translate.discardEdits"),
    })
  }

  async function openSegment(segId: number) {
    if (activeSeg?.id === segId) return
    if (!(await confirmDiscardEdits())) return
    const seq = ++openSegSeqRef.current
    try {
      const d = await translateApi.getSegment(segId)
      if (seq !== openSegSeqRef.current) return
      setActiveSeg(d)
      setEditOut(d.output_text ?? "")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function closeSegment() {
    if (!(await confirmDiscardEdits())) return
    openSegSeqRef.current += 1
    setActiveSeg(null)
  }

  async function saveSegment() {
    if (!activeSeg || saving) return
    setSaving(true)
    try {
      const d = await translateApi.putSegment(activeSeg.id, { output_text: editOut, reviewed: true })
      setActiveSeg(d)
      setSegments((list) =>
        list.map((s) =>
          s.id === d.id
            ? { ...s, reviewed: d.reviewed, output_preview: (d.output_text || "").slice(0, 200) }
            : s,
        ),
      )
      toast.success(t("translate.reviewSaved"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  const activeIdx = activeSeg ? filteredSegments.findIndex((s) => s.id === activeSeg.id) : -1

  async function jumpAdjacent(delta: number) {
    if (filteredSegments.length === 0) return
    const next = activeIdx < 0 ? filteredSegments[0] : filteredSegments[activeIdx + delta]
    if (next) await openSegment(next.id)
  }

  // Phím tắt (chỉ trong trang này): j/k hoặc ↑/↓ chuyển chương khi không gõ; Ctrl/⌘+S lưu.
  const keyHandlersRef = useRef({ jump: jumpAdjacent, save: saveSegment, hasSeg: false })
  useEffect(() => {
    keyHandlersRef.current = { jump: jumpAdjacent, save: saveSegment, hasSeg: activeSeg != null }
  })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return
      // Có dialog đang mở (xác nhận, đổi AI…) → không can thiệp.
      if (document.querySelector('[data-slot="dialog-content"]')) return
      const h = keyHandlersRef.current
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s") {
        if (!h.hasSeg) return
        e.preventDefault()
        void h.save()
        return
      }
      if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e.target)) return
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault()
        void h.jump(1)
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault()
        void h.jump(-1)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  if (loadError) {
    return (
      <PageShell>
        <p className="text-sm text-destructive">{loadError}</p>
      </PageShell>
    )
  }

  if (!work || !job) {
    return (
      <PageShell>
        <PageSkeleton />
      </PageShell>
    )
  }

  const isCompleted = job.status === "completed"
  const primary: "pause" | "send" | "resume" | null = active
    ? "pause"
    : isCompleted
      ? "send"
      : canResume
        ? "resume"
        : null

  const primaryAction =
    primary === "pause" ? (
      <Button type="button" disabled={busy} onClick={() => void handlePause()}>
        <Pause aria-hidden />
        {t("translate.pauseJob")}
      </Button>
    ) : primary === "send" ? (
      <Button type="button" disabled={busy} onClick={() => void handleSendTts()}>
        <Headphones aria-hidden />
        {t("translate.job.sendToListen")}
      </Button>
    ) : primary === "resume" ? (
      <Button type="button" disabled={busy} onClick={() => void handleResume()}>
        <Play aria-hidden />
        {t("translate.resume")}
      </Button>
    ) : null

  const secondaryActions = (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setSwitchOpen(true)}>
        <Cpu aria-hidden />
        {t("translate.job.switchAi")}
      </Button>
      <ActionMenu
        label={
          <>
            <Download aria-hidden />
            {exporting ? t("translate.job.exporting") : t("translate.job.export")}
          </>
        }
        disabled={exporting != null || !canExport}
      >
        <ActionMenuItem onSelect={() => void runExport("txt", translateApi.exportTxt)}>TXT</ActionMenuItem>
        <ActionMenuItem onSelect={() => void runExport("json", translateApi.exportJson)}>JSON</ActionMenuItem>
        <ActionMenuItem onSelect={() => void runExport("epub", (id) => translateApi.exportEpub(id))}>EPUB</ActionMenuItem>
        <ActionMenuItem onSelect={() => void runExport("epub-bilingual", (id) => translateApi.exportEpub(id, true))}>
          {t("translate.exportBilingual")}
        </ActionMenuItem>
      </ActionMenu>
      <ActionMenu
        label={
          <>
            <MoreHorizontal aria-hidden />
            <span className="sr-only">{t("translate.job.more")}</span>
          </>
        }
        showChevron={false}
      >
        {primary !== "resume" ? (
          <ActionMenuItem disabled={busy || !canResume} onSelect={() => void handleResume()}>
            {t("translate.resume")}
          </ActionMenuItem>
        ) : null}
        {primary !== "send" ? (
          <ActionMenuItem disabled={busy || !isCompleted} onSelect={() => void handleSendTts()}>
            {t("translate.job.sendToListen")}
          </ActionMenuItem>
        ) : null}
        <ActionMenuItem destructive disabled={busy || !canDelete} onSelect={() => void handleDelete()}>
          {t("translate.deleteJob")}
        </ActionMenuItem>
      </ActionMenu>
    </>
  )

  const langSrc = work.lang_src
  const langTgt = variant?.lang_tgt ?? work.lang_tgt

  return (
    <PageShell className="space-y-4">
      <PageHeader
        breadcrumbs={[
          { label: t("translate.job.crumbTranslate"), to: "/translate" },
          { label: work.title, to: `/translate/${wId}` },
          { label: t("translate.job.title", { id: job.id }) },
        ]}
        eyebrow={t("translate.job.eyebrow")}
        stage="translate"
        title={work.title}
        meta={
          <>
            {variant ? <span>{modeLabel(variant.mode)}</span> : null}
            <span className="font-mono text-[13px] uppercase">
              {langSrc} → {langTgt}
            </span>
            <span className="font-mono text-[13px]">{t("translate.job.title", { id: job.id })}</span>
          </>
        }
        secondaryActions={secondaryActions}
        primaryAction={primaryAction}
      />

      <JobStatusStrip
        job={job}
        active={active}
        flaggedCount={flaggedCount}
        connectionLost={active && pollFailures >= POLL_FAIL_WARN}
        quotaError={looksLikeQuotaError}
        busy={busy}
        onRetranslateFlagged={() => void handleRetranslateFlagged()}
        onShowFlagged={() => setSegFilter("flagged")}
      />

      <section
        aria-label={t("translate.job.workspaceLabel")}
        className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card lg:h-[calc(100dvh-8.5rem)] lg:min-h-[34rem] lg:flex-row"
      >
        <div className="flex h-[24rem] shrink-0 flex-col border-b border-border bg-muted/40 lg:h-auto lg:w-[340px] lg:border-r lg:border-b-0">
          <SegmentList
            segments={filteredSegments}
            totalCount={segments.length}
            activeId={activeSeg?.id ?? null}
            onOpen={(id) => void openSegment(id)}
            titleFor={titleFor}
            search={segSearch}
            onSearch={setSegSearch}
            filter={segFilter}
            onFilter={setSegFilter}
            counts={counts}
            qaFlags={qaFlagsPresent}
            qaFlag={qaFlag}
            onQaFlag={setQaFlag}
          />
          <p className="hidden border-t border-border px-4 py-2 text-[11px] text-muted-foreground lg:block">
            {t("translate.job.shortcuts")}
          </p>
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <ReviewPane
            segment={activeSeg}
            title={activeSeg ? titleFor(activeSeg.chapter_index) : ""}
            langSrc={langSrc}
            langTgt={langTgt}
            value={editOut}
            onChange={setEditOut}
            dirty={reviewDirty}
            saving={saving}
            onSave={() => void saveSegment()}
            onPrev={() => void jumpAdjacent(-1)}
            onNext={() => void jumpAdjacent(1)}
            hasPrev={activeIdx > 0}
            hasNext={filteredSegments.length > 0 && activeIdx < filteredSegments.length - 1}
            onClose={() => void closeSegment()}
            onRetranslateFlagged={(flag) => void handleRetranslateFlagged(flag ?? "")}
            retranslateDisabled={busy || active}
          />
        </div>
      </section>

      <SwitchAiDialog
        open={switchOpen}
        onOpenChange={setSwitchOpen}
        job={job}
        providers={providers}
        switchAiId={switchAiId}
        onSwitchAiId={setSwitchAiId}
        switchModel={switchModel}
        onSwitchModel={setSwitchModel}
        modelOptions={switchModelOptions}
        busy={busy}
        active={active}
        canResume={canResume}
        onApply={() => void handleApplyAiMidRun()}
        onResume={() => void handleResume()}
      />
      {confirmDialog}
    </PageShell>
  )
}
