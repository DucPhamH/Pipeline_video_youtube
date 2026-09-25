import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader, PageShell, SectionCard, SegmentedTabs } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { translateApi } from "../api"
import { StartTranslationModal } from "../components/StartTranslationModal"
import { TranslateStatusBadge } from "../components/TranslateStatusBadge"
import { useModeLabel } from "../components/ModeParamsFields"
import { jobCanDelete, jobCanResume, jobIsActive, useJobActions } from "../hooks/useJobActions"
import type { GlossaryTerm, Job, StyleProfile, Variant, Work } from "../types"

type Tab = "translate" | "glossary" | "source"

function autoModalSeenKey(workId: number) {
  return `translate.autoModalSeen.v1.${workId}`
}

export function TranslateWorkPage() {
  const t = useT()
  const navigate = useNavigate()
  const { workId } = useParams<{ workId: string }>()
  const id = Number(workId)
  const actions = useJobActions()
  const modeLabel = useModeLabel()

  const [work, setWork] = useState<Work | null>(null)
  const [jobsByVariant, setJobsByVariant] = useState<Record<number, Job | null>>({})
  const [glossary, setGlossary] = useState<GlossaryTerm[]>([])
  const [profiles, setProfiles] = useState<StyleProfile[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<Tab>("translate")

  const [srcTerm, setSrcTerm] = useState("")
  const [tgtTerm, setTgtTerm] = useState("")
  const [protectedTerm, setProtectedTerm] = useState(true)

  const [modalOpen, setModalOpen] = useState(false)
  const [modalVariantId, setModalVariantId] = useState<number | null>(null)

  const loadJobs = useCallback(async (w: Work) => {
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
    setJobsByVariant(Object.fromEntries(entries))
  }, [])

  const loadWork = useCallback(async () => {
    if (!Number.isFinite(id)) return
    try {
      const w = await translateApi.getWork(id)
      setWork(w)
      setGlossary(await translateApi.listGlossary(id))
      await loadJobs(w)

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
  }, [id, t, loadJobs])

  useEffect(() => {
    void loadWork()
    translateApi.listStyleProfiles().then(setProfiles).catch(() => setProfiles([]))
    // initial load only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  useEffect(() => {
    const active = Object.values(jobsByVariant).some((j) => jobIsActive(j))
    if (!active) return
    const timer = setInterval(async () => {
      if (!work) return
      await loadJobs(work)
    }, 1500)
    return () => clearInterval(timer)
  }, [jobsByVariant, work, loadJobs])

  function openModalFor(variantId: number | null) {
    setModalVariantId(variantId)
    setModalOpen(true)
  }

  function handleStarted(_variantId: number, jobId: number) {
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
    setBusy(true)
    const ok = await actions.remove(job.id, t("translate.deleteJobConfirm"))
    if (ok) setJobsByVariant((m) => ({ ...m, [variantId]: null }))
    setBusy(false)
  }

  async function handleRetranslate(variantId: number, job: Job) {
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


  async function handleAddGlossary() {
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

  async function handleDeleteGlossary(termId: number) {
    try {
      await translateApi.deleteGlossary(id, termId)
      setGlossary((g) => g.filter((x) => x.id !== termId))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  function jobStatusLabel(status: string) {
    if (status === "queued") return t("translate.statusQueued")
    if (status === "running") return t("translate.statusRunning")
    if (status === "completed") return t("translate.statusCompleted")
    if (status === "failed") return t("translate.statusFailed")
    if (status === "cancelled") return t("translate.statusCancelled")
    return status
  }

  function variantRow(v: Variant) {
    const job = jobsByVariant[v.id] ?? null
    const active = jobIsActive(job)
    const progressPct = job && job.total_segments > 0 ? Math.round((job.done_segments / job.total_segments) * 100) : 0
    return (
      <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">
            #{v.id} · {modeLabel(v.mode)}
            <span className="ml-2 text-xs font-normal text-muted-foreground">{v.lang_tgt}</span>
          </p>
          {job ? (
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <TranslateStatusBadge status={job.status} label={jobStatusLabel(job.status)} />
              <span>
                {job.done_segments}/{job.total_segments} {t("translate.chaptersShort")}
                {job.failed_segments ? ` · ${job.failed_segments} ${t("translate.failShort")}` : ""}
                {active ? ` · ${progressPct}%` : ""}
              </span>
            </p>
          ) : v.source_variant_id != null &&
            work?.variants.find((x) => x.id === v.source_variant_id)?.status !== "ready" ? (
            <p className="text-xs text-muted-foreground">{t("translate.waitingOnFull")}</p>
          ) : (
            <p className="text-xs text-muted-foreground">{t("translate.noJobYet")}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {job ? (
            <>
              <Link
                to={`/translate/${id}/jobs/${job.id}`}
                className="inline-flex h-8 items-center rounded-md border border-input px-2.5 text-xs font-medium hover:bg-muted"
              >
                {t("translate.openJob")}
              </Link>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy || !active}
                onClick={() => void handlePause(v.id, job)}
              >
                {t("translate.pauseJob")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy || active || !(jobCanResume(job) || jobCanDelete(job))}
                onClick={() => void handleRetranslate(v.id, job)}
              >
                {t("translate.retranslate")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy || !jobCanDelete(job)}
                onClick={() => void handleDelete(v.id, job)}
              >
                {t("translate.deleteJob")}
              </Button>
            </>
          ) : (
            <Button type="button" size="sm" onClick={() => openModalFor(v.id)}>
              {t("translate.startJob")}
            </Button>
          )}
          <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => void handleCloneVariant(v.id)}>
            {t("translate.cloneVariant")}
          </Button>
        </div>
      </li>
    )
  }

  if (loadError) {
    return (
      <PageShell>
        <p className="text-sm text-destructive">{loadError}</p>
      </PageShell>
    )
  }

  if (!work) {
    return (
      <PageShell>
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      </PageShell>
    )
  }

  return (
    <PageShell className="gap-4 space-y-4">
      <PageHeader
        eyebrow={
          <Link to="/translate" className="text-muted-foreground hover:text-foreground">
            {t("translate.backLibrary")}
          </Link>
        }
        title={work.title}
        description={`${work.author || "—"} · ${work.lang_src}→${work.lang_tgt} · ${work.chapters.length} ch`}
        actions={
          <Button type="button" onClick={() => openModalFor(null)}>
            {t("translate.newTranslation")}
          </Button>
        }
      />

      {work.missing_cleaned > 0 || work.unreviewed_chapters > 0 ? (
        <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          {[
            work.missing_cleaned > 0
              ? t("translate.qualityGateMissingCleaned", { count: String(work.missing_cleaned) })
              : null,
            work.unreviewed_chapters > 0
              ? t("translate.qualityGateUnreviewed", { count: String(work.unreviewed_chapters) })
              : null,
          ]
            .filter(Boolean)
            .join(" · ")}
          {" — "}
          {t("translate.qualityGateHint")}
        </p>
      ) : null}

      <SegmentedTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "translate", label: `${t("translate.variants")} (${work.variants.length})` },
          { value: "glossary", label: `${t("translate.glossary")}${glossary.length ? ` (${glossary.length})` : ""}` },
          { value: "source", label: `${t("translate.chapters")} (${work.chapters.length})` },
        ]}
      />

      {tab === "translate" ? (
        <SectionCard title={t("translate.variants")}>
          {work.variants.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("translate.noJobYet")}</p>
          ) : (
            <ul className="divide-y divide-border">{work.variants.map(variantRow)}</ul>
          )}

        </SectionCard>
      ) : null}

      {tab === "glossary" ? (
        <SectionCard title={t("translate.glossary")} description={t("translate.glossaryHint")}>
          <div className="mb-3 flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="g-src">{t("translate.termSrc")}</Label>
              <Input id="g-src" value={srcTerm} onChange={(e) => setSrcTerm(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="g-tgt">{t("translate.termTgt")}</Label>
              <Input id="g-tgt" value={tgtTerm} onChange={(e) => setTgtTerm(e.target.value)} />
            </div>
            <label className="flex items-center gap-2 pb-2 text-sm">
              <input type="checkbox" checked={protectedTerm} onChange={(e) => setProtectedTerm(e.target.checked)} />
              {t("translate.termProtected")}
            </label>
            <Button type="button" onClick={handleAddGlossary}>
              {t("translate.addTerm")}
            </Button>
          </div>
          {glossary.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("translate.glossaryEmpty")}</p>
          ) : (
            <ul className="max-h-[60vh] divide-y divide-border overflow-y-auto text-sm">
              {glossary.map((g) => (
                <li key={g.id} className="flex items-center justify-between gap-2 py-2">
                  <span>
                    <span className="font-medium">{g.source_term}</span>
                    {" → "}
                    {g.target_term}
                    {g.protected ? (
                      <span className="ml-2 text-xs text-muted-foreground">({t("translate.termProtected")})</span>
                    ) : null}
                  </span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => handleDeleteGlossary(g.id)}>
                    {t("common.confirmDelete")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      ) : null}

      {tab === "source" ? (
        <SectionCard title={t("translate.chapters")}>
          <ul className="max-h-[70vh] divide-y divide-border overflow-y-auto text-sm">
            {work.chapters.map((c) => (
              <li key={c.id} className="py-2">
                <span className="font-medium">
                  #{c.index} {c.title || "—"}
                </span>
                <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{c.text_preview}</p>
              </li>
            ))}
          </ul>
        </SectionCard>
      ) : null}

      <StartTranslationModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        work={work}
        existingVariantId={modalVariantId}
        styleProfiles={profiles}
        onStarted={handleStarted}
      />
    </PageShell>
  )
}
