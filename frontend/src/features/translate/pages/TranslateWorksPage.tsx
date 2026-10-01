import { useEffect, useMemo, useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { AlertTriangle, BookPlus, ChevronRight, FileText, Library, MoreHorizontal, Search, Settings2, Upload } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Progress } from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { PageHeader, PageShell, SegmentedTabs } from "@/components/PageChrome"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { BookCover } from "@/components/BookCover"
import { EmptyState } from "@/components/EmptyState"
import { StatusPill } from "@/components/StatusPill"
import { Skeleton } from "@/components/Skeleton"
import { useConfirm } from "@/components/useConfirm"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { ApiError } from "@/api/client"
import { translateApi } from "../api"
import { modeVisual, useModeTitle } from "../components/variantVisual"
import { useStatusLabels } from "../hooks/useStatusLabels"
import type { Inbox, InboxItem, Job, Work } from "../types"

type Filter = "all" | "running" | "review" | "ready" | "new"

const STATUS_RANK: Record<string, number> = { running: 5, queued: 4, failed: 3, ready: 2, pending: 1 }

/** Trạng thái tiêu biểu của work = variant "nóng" nhất (đang chạy > lỗi > xong > chưa chạy). */
function workStatus(w: Work): string {
  let best = ""
  for (const v of w.variants) {
    if ((STATUS_RANK[v.status] ?? 0) > (STATUS_RANK[best] ?? 0)) best = v.status
  }
  return best || "pending"
}

export function TranslateWorksPage() {
  const t = useT()
  const modeTitle = useModeTitle()
  const { jobStatusLabel, variantStatusLabel } = useStatusLabels()
  const [confirm, confirmDialog] = useConfirm()
  const [items, setItems] = useState<Work[]>([])
  const [loading, setLoading] = useState(true)
  const [importKind, setImportKind] = useState<"txt" | "epub">("txt")
  /** Đổi key để React dựng lại <input type=file> → xoá file đã chọn. */
  const [fileInputKey, setFileInputKey] = useState(0)
  const [inbox, setInbox] = useState<Inbox | null>(null)
  const [runningJobs, setRunningJobs] = useState<Record<number, Job>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [author, setAuthor] = useState("")
  const [langSrc, setLangSrc] = useState("zh")
  const [text, setText] = useState("")
  const [epubFile, setEpubFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [search, setSearch] = useState("")
  const [filter, setFilter] = useState<Filter>("all")

  const reviewWorkIds = useMemo(() => new Set(inbox?.needs_review.map((r) => r.work_id) ?? []), [inbox])
  const readyWorkIds = useMemo(() => new Set(inbox?.ready_export.map((r) => r.work_id) ?? []), [inbox])

  function matchesFilter(w: Work, f: Filter): boolean {
    const st = workStatus(w)
    if (f === "running") return st === "running" || st === "queued"
    if (f === "review") return reviewWorkIds.has(w.id)
    if (f === "ready") return readyWorkIds.has(w.id) || st === "ready"
    if (f === "new") return w.variants.every((v) => v.latest_job_id == null)
    return true
  }

  const q = search.trim().toLowerCase()
  const searched = items.filter((w) => !q || w.title.toLowerCase().includes(q) || w.author.toLowerCase().includes(q))
  const filteredItems = searched.filter((w) => matchesFilter(w, filter))
  const countFor = (f: Filter) => searched.filter((w) => matchesFilter(w, f)).length

  function loadInbox() {
    translateApi
      .getInbox()
      .then((ib) => {
        setInbox(ib)
        // Tiến độ thật cho các job đang chạy (ít, nên gọi từng cái).
        const ids = ib.running.map((r) => r.job_id).filter((x): x is number => x != null)
        void Promise.all(ids.map((id) => translateApi.getJob(id).catch(() => null))).then((jobs) => {
          const map: Record<number, Job> = {}
          for (const j of jobs) if (j) map[j.id] = j
          setRunningJobs(map)
        })
      })
      .catch(() => setInbox(null))
  }

  function load() {
    setLoading(true)
    setLoadError(null)
    translateApi
      .listWorks()
      .then((r) => setItems(r.items))
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("app.unknownError")))
      .finally(() => setLoading(false))
    loadInbox()
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function resetImportForm() {
    setImportOpen(false)
    setTitle("")
    setAuthor("")
    setText("")
    setEpubFile(null)
    setFileInputKey((k) => k + 1)
  }

  function handleImportSubmit(e: FormEvent) {
    e.preventDefault()
    if (saving) return
    void (importKind === "epub" ? handleImportEpub() : handleImport())
  }

  async function afterImport(work: Work) {
    toast.success(t("translate.importOk"))
    resetImportForm()
    setItems((prev) => [work, ...prev.filter((w) => w.id !== work.id)])
    loadInbox()
  }

  async function handleImport() {
    if (!title.trim() || !text.trim()) {
      toast.error(t("translate.importNeedFields"))
      return
    }
    setSaving(true)
    try {
      const work = await translateApi.importTxt({
        title: title.trim(),
        author: author.trim(),
        lang_src: langSrc.trim() || "zh",
        lang_tgt: "vi",
        text,
      })
      await afterImport(work)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  async function handleImportEpub() {
    if (!epubFile) {
      toast.error(t("translate.importEpubNeedFile"))
      return
    }
    setSaving(true)
    try {
      const work = await translateApi.importEpub({
        file: epubFile,
        title: title.trim(),
        author: author.trim(),
        lang_src: langSrc.trim() || "zh",
      })
      await afterImport(work)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteWork(id: number) {
    const confirmed = await confirm({
      title: t("common.deleteTitle"),
      description: t("translate.deleteWorkConfirm"),
    })
    if (!confirmed) return
    setDeletingId(id)
    try {
      await translateApi.deleteWork(id)
      toast.success(t("translate.workDeleted"))
      setItems((prev) => prev.filter((w) => w.id !== id))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setDeletingId(null)
    }
  }

  const header = (
    <PageHeader
      eyebrow={t("translate.hub.eyebrow")}
      stage="translate"
      title={t("translate.title")}
      description={t("translate.subtitle")}
      secondaryActions={
        <Link to="/translate/settings" className={buttonVariants({ variant: "outline" })}>
          <Settings2 aria-hidden />
          {t("translate.settings")}
        </Link>
      }
      primaryAction={
        <Button type="button" onClick={() => setImportOpen(true)}>
          <Upload aria-hidden />
          {t("translate.importOpen")}
        </Button>
      }
    />
  )

  if (loadError) {
    return (
      <PageShell>
        {header}
        <EmptyState
          icon={AlertTriangle}
          tone="neutral"
          title={loadError}
          action={
            <Button type="button" variant="outline" onClick={load}>
              {t("translate.reload")}
            </Button>
          }
        />
      </PageShell>
    )
  }

  const needsYou: { key: string; label: string; rows: InboxItem[] }[] = inbox
    ? [
        { key: "running", label: t("translate.inboxRunning"), rows: inbox.running },
        { key: "review", label: t("translate.inboxReview"), rows: inbox.needs_review },
        { key: "ready", label: t("translate.inboxReady"), rows: inbox.ready_export },
      ].filter((b) => b.rows.length > 0)
    : []

  return (
    <PageShell>
      {header}

      {needsYou.length > 0 ? (
        <section aria-labelledby="needs-you" className="rounded-[16px] border border-border bg-card p-5">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="needs-you" className="flex items-center gap-2 text-[17px] font-semibold">
              <span className="size-2 rounded-full bg-live" aria-hidden />
              {t("translate.hub.needsYou")}
            </h2>
            <p className="text-sm text-muted-foreground">{t("translate.inboxHint")}</p>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {needsYou.map((bucket) => (
              <div key={bucket.key} className="min-w-0 space-y-2">
                <p className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
                  {bucket.label} <span className="font-mono">{bucket.rows.length}</span>
                </p>
                <ul className="stagger space-y-1.5">
                  {bucket.rows.map((row) => {
                    const vis = modeVisual(row.mode)
                    const Icon = vis.icon
                    const job = row.job_id != null ? runningJobs[row.job_id] : undefined
                    const pct = job && job.total_segments > 0 ? (job.done_segments / job.total_segments) * 100 : null
                    const status = row.job_status ?? row.variant_status
                    return (
                      <li key={`${row.work_id}-${row.variant_id}`}>
                        <Link
                          to={row.job_id ? `/translate/${row.work_id}/jobs/${row.job_id}` : `/translate/${row.work_id}`}
                          className="group flex items-center gap-3 rounded-xl border border-transparent px-2.5 py-2 transition-colors hover:border-border hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                        >
                          <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", vis.tint)}>
                            <Icon className="size-4" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium">{row.work_title}</span>
                            <span className="block truncate text-xs text-muted-foreground">
                              {modeTitle(row.mode)}
                              {row.unreviewed ? ` · ${t("translate.hub.unreviewedCount", { count: row.unreviewed })}` : ""}
                            </span>
                            {bucket.key === "running" ? (
                              <Progress value={pct} tone="translate" live size="sm" className="mt-1.5" />
                            ) : null}
                          </span>
                          <StatusPill
                            status={status}
                            label={row.job_status ? jobStatusLabel(row.job_status) : variantStatusLabel(row.variant_status)}
                            className="hidden sm:inline-flex"
                          />
                          <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section aria-labelledby="tr-library" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="tr-library" className="font-display text-[22px]">
            {t("translate.library")}
            {items.length ? <span className="ml-2 font-mono text-sm text-muted-foreground">{items.length}</span> : null}
          </h2>
          {items.length > 0 ? (
            <div className="relative w-full sm:w-72">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("translate.searchWorks")}
                aria-label={t("translate.searchWorks")}
                className="pl-8"
              />
            </div>
          ) : null}
        </div>

        {items.length > 0 ? (
          <SegmentedTabs
            value={filter}
            onChange={setFilter}
            items={[
              { value: "all", label: t("translate.filterAll"), count: countFor("all") },
              { value: "running", label: t("translate.hub.filterRunning"), count: countFor("running") },
              { value: "review", label: t("translate.hub.filterReview"), count: countFor("review") },
              { value: "ready", label: t("translate.hub.filterReady"), count: countFor("ready") },
              { value: "new", label: t("translate.hub.filterNew"), count: countFor("new") },
            ]}
          />
        ) : null}

        {loading && items.length === 0 ? (
          <div className="grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" role="status">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="aspect-[2/3] w-full rounded-xl" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-[16px] border border-dashed border-border bg-card">
            <EmptyState
              icon={Library}
              tone="translate"
              title={t("translate.hub.emptyTitle")}
              hint={t("translate.empty")}
              action={
                <Button type="button" onClick={() => setImportOpen(true)}>
                  <Upload aria-hidden />
                  {t("translate.importOpen")}
                </Button>
              }
            />
          </div>
        ) : filteredItems.length === 0 ? (
          <EmptyState icon={Search} tone="neutral" compact title={t("translate.worksFilterEmpty")} />
        ) : (
          <ul className="stagger grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {filteredItems.map((w) => {
              const st = workStatus(w)
              const live = st === "running" || st === "queued"
              const runRow = inbox?.running.find((r) => r.work_id === w.id)
              const job = runRow?.job_id != null ? runningJobs[runRow.job_id] : undefined
              const pct = job && job.total_segments > 0 ? (job.done_segments / job.total_segments) * 100 : null
              const neverStarted = w.variants.every((v) => v.latest_job_id == null)
              const gate = w.missing_cleaned > 0 || w.unreviewed_chapters > 0
              return (
                <li key={w.id} className="relative min-w-0">
                  <Link
                    to={`/translate/${w.id}`}
                    className="group block rounded-xl focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                  >
                    <BookCover title={w.title} subtitle={`${w.lang_src} → ${w.lang_tgt}`} />
                    <div className="mt-3 space-y-1.5">
                      <p className="font-display line-clamp-2 text-[17px] leading-snug group-hover:text-accent-foreground">
                        {w.title}
                      </p>
                      <p className="truncate text-[13px] text-muted-foreground">
                        {w.author || "—"} · <span className="font-mono">{w.chapters.length}</span> {t("translate.chaptersShort")}
                      </p>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="inline-flex h-6 items-center rounded-full bg-accent px-2 font-mono text-xs font-semibold text-accent-foreground">
                          {w.lang_src}→{w.lang_tgt}
                        </span>
                        <StatusPill
                          status={neverStarted ? "idle" : st}
                          label={neverStarted ? t("translate.variantStatusPending") : variantStatusLabel(st)}
                        />
                        {gate ? (
                          <span
                            className="inline-flex size-6 items-center justify-center rounded-full bg-warning-soft text-warning"
                            title={t("translate.qualityGateHint")}
                          >
                            <AlertTriangle className="size-3.5" aria-label={t("translate.qualityGateHint")} />
                          </span>
                        ) : null}
                      </div>
                      {live ? <Progress value={pct} tone="translate" live size="sm" label={t("translate.statusRunning")} /> : null}
                    </div>
                  </Link>
                  <div className="absolute top-2 right-2">
                    <ActionMenu
                      label={<MoreHorizontal className="size-4" aria-label={t("novel.moreActions")} />}
                      variant="outline"
                      showChevron={false}
                      disabled={deletingId === w.id}
                    >
                      <ActionMenuItem destructive onSelect={() => void handleDeleteWork(w.id)}>
                        {t("common.confirmDelete")}
                      </ActionMenuItem>
                    </ActionMenu>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <Dialog open={importOpen} onOpenChange={(o) => (o ? setImportOpen(true) : !saving && setImportOpen(false))}>
        <DialogContent className="sm:max-w-xl">
          <form onSubmit={handleImportSubmit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <BookPlus className="size-5 text-stage-translate" aria-hidden />
                {t("translate.hub.importTitle")}
              </DialogTitle>
              <DialogDescription>
                {importKind === "txt" ? t("translate.importHint") : t("translate.importEpubHint")}
              </DialogDescription>
            </DialogHeader>

            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={t("translate.importOpen")}>
              {(
                [
                  { value: "txt", icon: FileText, label: t("translate.importKindTxt") },
                  { value: "epub", icon: BookPlus, label: t("translate.importKindEpub") },
                ] as const
              ).map((k) => (
                <button
                  key={k.value}
                  type="button"
                  role="radio"
                  aria-checked={importKind === k.value}
                  onClick={() => setImportKind(k.value)}
                  className={cn(
                    "flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                    importKind === k.value
                      ? "border-primary bg-accent text-accent-foreground"
                      : "border-border hover:bg-muted",
                  )}
                >
                  <k.icon className="size-4 shrink-0" aria-hidden />
                  {k.label}
                </button>
              ))}
            </div>

            <div className="grid gap-3 sm:grid-cols-[1fr_1fr_6rem]">
              <div className="space-y-1.5">
                <Label htmlFor="tr-title">
                  {importKind === "epub" ? t("translate.fieldTitleOptional") : t("translate.fieldTitle")}
                </Label>
                <Input id="tr-title" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tr-author">{t("translate.fieldAuthor")}</Label>
                <Input id="tr-author" value={author} onChange={(e) => setAuthor(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tr-lang">{t("translate.fieldLangSrc")}</Label>
                <Input id="tr-lang" className="font-mono" value={langSrc} onChange={(e) => setLangSrc(e.target.value)} />
              </div>
            </div>

            {importKind === "txt" ? (
              <div className="space-y-1.5">
                <Label htmlFor="tr-text">{t("translate.fieldText")}</Label>
                <Textarea
                  id="tr-text"
                  rows={10}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="max-h-[40vh] font-mono text-[13px]"
                />
              </div>
            ) : (
              <label
                htmlFor="tr-epub"
                className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-muted/40 px-4 py-8 text-center transition-colors hover:bg-muted"
              >
                <Upload className="size-6 text-stage-translate" aria-hidden />
                <span className="text-sm font-medium">{epubFile ? epubFile.name : t("translate.importEpubFile")}</span>
                <span className="text-xs text-muted-foreground">.epub</span>
                <input
                  key={fileInputKey}
                  id="tr-epub"
                  type="file"
                  accept=".epub,application/epub+zip"
                  className="sr-only"
                  onChange={(e) => setEpubFile(e.target.files?.[0] ?? null)}
                />
              </label>
            )}

            <DialogFooter>
              <Button type="button" variant="ghost" disabled={saving} onClick={() => setImportOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={saving || (importKind === "epub" && !epubFile)}>
                {saving
                  ? t("common.saving")
                  : importKind === "epub"
                    ? t("translate.importEpub")
                    : t("translate.importSubmit")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      {confirmDialog}
    </PageShell>
  )
}
