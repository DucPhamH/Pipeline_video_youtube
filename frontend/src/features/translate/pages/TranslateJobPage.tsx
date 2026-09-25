import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { PageHeader, PageShell, SectionCard, SegmentedTabs } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { cn } from "@/lib/utils"
import { translateApi } from "../api"
import { TranslateStatusBadge } from "../components/TranslateStatusBadge"
import { jobCanDelete, jobCanResume, jobIsActive, useJobActions } from "../hooks/useJobActions"
import { getCatalogEntry } from "../providerProfiles"
import type { AiProvider, Job, Segment, SegmentDetail, Variant, Work } from "../types"

type SegFilter = "all" | "pending" | "done" | "failed" | "reviewed"
const PAGE_SIZE = 40
const QUOTA_ERROR_RE = /429|quota|rate.?limit|insufficient/i

export function TranslateJobPage() {
  const t = useT()
  const navigate = useNavigate()
  const { workId, jobId } = useParams<{ workId: string; jobId: string }>()
  const wId = Number(workId)
  const jId = Number(jobId)
  const actions = useJobActions()

  const [work, setWork] = useState<Work | null>(null)
  const [variant, setVariant] = useState<Variant | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [segments, setSegments] = useState<Segment[]>([])
  const [activeSeg, setActiveSeg] = useState<SegmentDetail | null>(null)
  const [editOut, setEditOut] = useState("")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [providers, setProviders] = useState<AiProvider[]>([])
  const [switchAiId, setSwitchAiId] = useState<number | null>(null)
  const [switchModel, setSwitchModel] = useState("")

  const [segFilter, setSegFilter] = useState<SegFilter>("all")
  const [segSearch, setSegSearch] = useState("")
  const [segPage, setSegPage] = useState(0)

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

  useEffect(() => {
    if (!job || !jobIsActive(job)) return
    const timer = setInterval(async () => {
      try {
        const j = await translateApi.getJob(job.id)
        setJob(j)
        setSegments(await translateApi.listSegments(j.id))
      } catch {
        /* ignore poll errors */
      }
    }, 1200)
    return () => clearInterval(timer)
  }, [job])

  const lastToastRef = useRef<{ id: number; status: string }>({ id: 0, status: "" })
  useEffect(() => {
    if (!job) return
    const prev = lastToastRef.current
    if (prev.id === job.id && prev.status === job.status) return
    const prevStatus = prev.id === job.id ? prev.status : ""
    lastToastRef.current = { id: job.id, status: job.status }
    if (!prevStatus || prevStatus === job.status) return
    if (job.status === "completed") toast.success(t("translate.jobDone"))
    else if (job.status === "failed") toast.error(job.error || t("translate.jobFailed"))
    else if (job.status === "cancelled") toast.message(t("translate.jobStopped"))
    else if (job.status === "running") toast.message(t("translate.jobRunning"))
  }, [job, t])

  useEffect(() => {
    setSegPage(0)
  }, [segFilter, segSearch])

  const filteredSegments = useMemo(() => {
    const q = segSearch.trim().toLowerCase()
    return segments.filter((s) => {
      if (segFilter === "pending" && !["pending", "queued"].includes(s.status)) return false
      if (segFilter === "done" && !["done", "skipped_cache"].includes(s.status)) return false
      if (segFilter === "failed" && s.status !== "failed") return false
      if (segFilter === "reviewed" && !s.reviewed) return false
      if (q) {
        const blob = `#${s.chapter_index} ${s.status} ${s.output_preview} ${s.error ?? ""}`.toLowerCase()
        if (!blob.includes(q)) return false
      }
      return true
    })
  }, [segments, segFilter, segSearch])

  const pageCount = Math.max(1, Math.ceil(filteredSegments.length / PAGE_SIZE))
  const pageSafe = Math.min(segPage, pageCount - 1)
  const pageItems = filteredSegments.slice(pageSafe * PAGE_SIZE, pageSafe * PAGE_SIZE + PAGE_SIZE)

  const progressPct = job && job.total_segments > 0 ? Math.round((job.done_segments / job.total_segments) * 100) : 0
  const active = jobIsActive(job)
  const canResume = jobCanResume(job)
  const canDelete = jobCanDelete(job)
  const looksLikeQuotaError = Boolean(job?.error && QUOTA_ERROR_RE.test(job.error))
  const isMultiAi = (job?.provider_slots?.length ?? 0) >= 2
  const isFallback = isMultiAi && job?.ai_mode === "fallback"

  function jobStatusLabel(status: string) {
    if (status === "queued") return t("translate.statusQueued")
    if (status === "running") return t("translate.statusRunning")
    if (status === "completed") return t("translate.statusCompleted")
    if (status === "failed") return t("translate.statusFailed")
    if (status === "cancelled") return t("translate.statusCancelled")
    return status
  }

  function segmentStatusLabel(status: string) {
    if (status === "pending" || status === "queued") return t("translate.filterPending")
    if (status === "done" || status === "skipped_cache") return t("translate.filterDone")
    if (status === "failed") return t("translate.filterFailed")
    return status
  }

  async function handlePause() {
    if (!job) return
    setBusy(true)
    const j = await actions.pause(job.id)
    if (j) {
      setJob(j)
      setSegments(await translateApi.listSegments(j.id))
    }
    setBusy(false)
  }

  useEffect(() => {
    if (!job) return
    setSwitchModel(job.model || "")
  }, [job?.id, job?.model])

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
    if (j) setJob(j)
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
    if (j) setJob(j)
    setBusy(false)
  }

  async function handleDelete() {
    if (!job) return
    const ok = await actions.remove(job.id, t("translate.deleteJobConfirm"))
    if (ok) navigate(`/translate/${wId}`)
  }

  async function handleExport() {
    if (!variant) return
    try {
      await translateApi.exportTxt(variant.id)
      toast.success(t("translate.exportOk"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function handleExportJson() {
    if (!variant) return
    try {
      await translateApi.exportJson(variant.id)
      toast.success(t("translate.exportOk"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function openSegment(segId: number) {
    try {
      const d = await translateApi.getSegment(segId)
      setActiveSeg(d)
      setEditOut(d.output_text ?? "")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function saveSegment() {
    if (!activeSeg) return
    setBusy(true)
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
      setBusy(false)
    }
  }

  async function jumpAdjacent(delta: number) {
    if (!activeSeg || filteredSegments.length === 0) return
    const idx = filteredSegments.findIndex((s) => s.id === activeSeg.id)
    const next = filteredSegments[idx < 0 ? 0 : idx + delta]
    if (next) await openSegment(next.id)
  }

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
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      </PageShell>
    )
  }

  return (
    <PageShell className="gap-4 space-y-4">
      <div className="sticky top-14 z-30 -mx-4 border-b border-border bg-background/95 px-4 py-3 backdrop-blur-sm sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <PageHeader
          className="gap-3"
          eyebrow={
            <Link to={`/translate/${wId}`} className="text-muted-foreground hover:text-foreground">
              ← {work.title}
            </Link>
          }
          title={t("translate.jobDetailTitle", { id: String(job.id) })}
          description={variant ? `${variant.mode} · ${variant.lang_tgt} · ${job.model}` : job.model}
        />

        <div className="mt-3 space-y-2 rounded-md border border-border bg-muted/40 px-3 py-2.5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0 space-y-0.5">
              <p className="flex items-center gap-1.5 text-sm font-medium">
                <TranslateStatusBadge status={job.status} label={jobStatusLabel(job.status)} />
                <span className="font-normal text-muted-foreground">
                  {job.done_segments}/{job.total_segments} {t("translate.chaptersShort")}
                  {job.failed_segments ? ` · ${job.failed_segments} ${t("translate.failShort")}` : ""}
                </span>
              </p>
            </div>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{progressPct}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-background">
            <div
              className={cn(
                "h-full rounded-full transition-[width] duration-300",
                job.status === "failed" ? "bg-destructive" : job.status === "cancelled" ? "bg-amber-500" : "bg-primary",
              )}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {job.error ? <p className="text-xs text-destructive">{job.error}</p> : null}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" disabled={busy || !active} onClick={() => void handlePause()}>
            {t("translate.pauseJob")}
          </Button>
          <Button type="button" variant="outline" disabled={busy || !canResume} onClick={() => void handleResume()}>
            {t("translate.resume")}
          </Button>
          <Button type="button" variant="outline" disabled={busy || !canDelete} onClick={() => void handleDelete()}>
            {t("translate.deleteJob")}
          </Button>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!(job.status === "completed" || variant?.status === "ready")}
              onClick={() => void handleExport()}
            >
              TXT
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!(job.status === "completed" || variant?.status === "ready")}
              onClick={() => void handleExportJson()}
            >
              JSON
            </Button>
          </div>
        </div>

        {looksLikeQuotaError ? (
          <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            {t("translate.quotaErrorBanner")}
          </p>
        ) : null}

        {isMultiAi ? (
          <div className="mt-3 space-y-1 border-t border-border pt-3">
            <p className="text-xs font-medium text-muted-foreground">
              {t(isFallback ? "translate.fallbackJobLabel" : "translate.poolJobLabel")}
            </p>
            <ul className="flex flex-wrap gap-1.5">
              {job.provider_slots!.map((s) => {
                const isActive = isFallback && s.slot_index === job.current_slot_index
                return (
                  <li
                    key={s.slot_index}
                    className={cn(
                      "rounded-md border px-2 py-1 text-xs",
                      isActive
                        ? "border-emerald-500/40 bg-emerald-500/10 font-medium text-emerald-700 dark:text-emerald-300"
                        : "border-border bg-muted/40",
                    )}
                  >
                    {s.label || s.model}
                    {s.requires_api_key && !s.has_api_key ? ` — ${t("translate.noKey")}` : ""}
                  </li>
                )
              })}
            </ul>
            <p className="text-xs text-muted-foreground">
              {t(isFallback ? "translate.fallbackNoSwitchHint" : "translate.poolNoSwitchHint")}
            </p>
          </div>
        ) : (
        <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-border pt-3">
          <label className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-xs">
            <span className="text-xs font-medium text-muted-foreground">{t("translate.switchAi")}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm"
              value={switchAiId ?? ""}
              onChange={(e) => {
                const id = e.target.value ? Number(e.target.value) : null
                setSwitchAiId(id)
                if (id != null) {
                  const p = providers.find((x) => x.id === id)
                  if (p) setSwitchModel(p.model)
                } else if (job) {
                  setSwitchModel(job.model || "")
                }
              }}
            >
              <option value="">{t("translate.switchAiKeep")}</option>
              {[...providers]
                .sort((a, b) => Number(a.kind === "mock") - Number(b.kind === "mock"))
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                    {p.kind === "mock" ? ` ${t("translate.mockSuffix")}` : ""}
                    {p.requires_api_key && !p.has_api_key ? ` — ${t("translate.noKey")}` : ""}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-xs">
            <span className="text-xs font-medium text-muted-foreground">{t("translate.jobModel")}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-2.5 font-mono text-xs"
              value={switchModelOptions.includes(switchModel) ? switchModel : "__custom__"}
              onChange={(e) => {
                const v = e.target.value
                if (v === "__custom__") setSwitchModel("")
                else setSwitchModel(v)
              }}
            >
              {switchModelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              <option value="__custom__">{t("settings.customModel")}</option>
            </select>
          </label>
          {!switchModelOptions.includes(switchModel) || switchModel === "" ? (
            <Input
              value={switchModel}
              onChange={(e) => setSwitchModel(e.target.value)}
              className="h-9 max-w-xs font-mono text-xs"
              placeholder="model-id"
            />
          ) : null}
          <Button
            type="button"
            variant="secondary"
            disabled={
              busy ||
              !active ||
              (switchAiId == null && (!switchModel.trim() || switchModel.trim() === job.model))
            }
            onClick={() => void handleApplyAiMidRun()}
          >
            {t("translate.applyAiMidRun")}
          </Button>
          <p className="basis-full text-xs text-muted-foreground">{t("translate.switchAiHint")}</p>
        </div>
        )}
      </div>

      <div className="grid min-h-[28rem] gap-4 lg:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)] lg:items-stretch">
        <SectionCard
          title={t("translate.segments")}
          description={t("translate.segmentsListHint", { shown: pageItems.length, total: filteredSegments.length })}
        >
          <div className="mb-3 flex flex-col gap-2">
            <Input
              value={segSearch}
              onChange={(e) => setSegSearch(e.target.value)}
              placeholder={t("translate.segmentSearch")}
              className="h-8"
            />
            <SegmentedTabs
              value={segFilter}
              onChange={setSegFilter}
              className="w-full"
              items={[
                { value: "all", label: t("translate.filterAll") },
                { value: "pending", label: t("translate.filterPending") },
                { value: "done", label: t("translate.filterDone") },
                { value: "failed", label: t("translate.filterFailed") },
                { value: "reviewed", label: t("translate.filterReviewed") },
              ]}
            />
          </div>

          {segments.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("translate.segmentsEmpty")}</p>
          ) : pageItems.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("translate.segmentsFilterEmpty")}</p>
          ) : (
            <ul className="max-h-[min(60vh,32rem)] divide-y divide-border overflow-y-auto lg:max-h-[calc(100vh-22rem)]">
              {pageItems.map((s) => {
                const isActive = activeSeg?.id === s.id
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      className={cn(
                        "flex w-full flex-col gap-0.5 px-1 py-2 text-left text-sm transition-colors",
                        isActive ? "bg-muted text-foreground" : "hover:bg-muted/60",
                      )}
                      onClick={() => openSegment(s.id)}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-medium">#{s.chapter_index}</span>
                        <span className="flex shrink-0 items-center gap-1.5">
                          <TranslateStatusBadge status={s.status} label={segmentStatusLabel(s.status)} />
                          {s.reviewed ? (
                            <span className="text-xs text-muted-foreground">{t("translate.reviewed")}</span>
                          ) : null}
                        </span>
                      </span>
                      {s.status === "failed" && s.error ? (
                        <span className="line-clamp-2 text-xs text-destructive">{s.error}</span>
                      ) : s.output_preview ? (
                        <span className="line-clamp-1 text-xs text-muted-foreground">{s.output_preview}</span>
                      ) : null}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}

          {filteredSegments.length > PAGE_SIZE ? (
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-border pt-3 text-xs">
              <Button type="button" variant="outline" size="sm" disabled={pageSafe <= 0} onClick={() => setSegPage((p) => Math.max(0, p - 1))}>
                {t("common.prev")}
              </Button>
              <span className="text-muted-foreground">
                {pageSafe + 1}/{pageCount}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={pageSafe >= pageCount - 1}
                onClick={() => setSegPage((p) => Math.min(pageCount - 1, p + 1))}
              >
                {t("common.next")}
              </Button>
            </div>
          ) : null}
        </SectionCard>

        <SectionCard
          title={activeSeg ? t("translate.reviewTitle", { index: activeSeg.chapter_index }) : t("translate.reviewPick")}
          description={activeSeg ? t("translate.reviewHint") : t("translate.reviewPickHint")}
          actions={
            activeSeg ? (
              <div className="flex gap-1">
                <Button type="button" variant="ghost" size="sm" onClick={() => jumpAdjacent(-1)}>
                  {t("common.prev")}
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => jumpAdjacent(1)}>
                  {t("common.next")}
                </Button>
              </div>
            ) : null
          }
        >
          {!activeSeg ? (
            <p className="text-sm text-muted-foreground">{t("translate.reviewPickHint")}</p>
          ) : (
            <>
              {activeSeg.error ? <p className="mb-3 text-xs text-destructive">{activeSeg.error}</p> : null}
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>{t("translate.source")}</Label>
                  <pre className="h-[min(55vh,32rem)] overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/40 p-3 text-xs leading-relaxed">
                    {activeSeg.source_text}
                  </pre>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="seg-out">{t("translate.output")}</Label>
                  <Textarea
                    id="seg-out"
                    value={editOut}
                    onChange={(e) => setEditOut(e.target.value)}
                    className="h-[min(55vh,32rem)] resize-none overflow-y-auto font-mono text-xs [field-sizing:fixed]"
                  />
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button type="button" disabled={busy} onClick={saveSegment}>
                  {busy ? t("common.saving") : t("translate.saveReview")}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setActiveSeg(null)}>
                  {t("common.close")}
                </Button>
              </div>
            </>
          )}
        </SectionCard>
      </div>
    </PageShell>
  )
}
