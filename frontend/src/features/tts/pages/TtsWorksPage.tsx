import { useEffect, useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { Headphones, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
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
import { BookCover } from "@/components/BookCover"
import { EmptyState } from "@/components/EmptyState"
import { StatusPill } from "@/components/StatusPill"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { ttsApi, type TtsWork, type TtsWorkListItem } from "../api"

const selectClass =
  "h-10 w-full rounded-[10px] border border-input bg-card px-3 text-sm focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"

function toListItem(work: TtsWork): TtsWorkListItem {
  const job = work.readings[0]?.latest_job ?? null
  return {
    id: work.id,
    title: work.title,
    author: work.author,
    lang: work.lang,
    source_type: work.source_type,
    chapter_count: work.chapters.length,
    latest_status: job?.status ?? work.readings[0]?.status ?? null,
    latest_done: job?.done_segments ?? 0,
    latest_total: job?.total_segments ?? 0,
  }
}

export function TtsWorksPage() {
  const t = useT()
  const [items, setItems] = useState<TtsWorkListItem[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [title, setTitle] = useState("")
  const [author, setAuthor] = useState("")
  const [lang, setLang] = useState("vi")
  const [text, setText] = useState("")
  const [epubFile, setEpubFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [importOpen, setImportOpen] = useState(false)
  const [importKind, setImportKind] = useState<"txt" | "epub">("txt")
  /** Đổi key để dựng lại <input type=file> → xoá file đã chọn sau khi import. */
  const [fileInputKey, setFileInputKey] = useState(0)

  useEffect(() => {
    ttsApi
      .listWorks()
      .then((r) => setItems(r.items))
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("app.unknownError")))
      .finally(() => setLoading(false))
  }, [t])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (saving) return
    void (importKind === "epub" ? handleEpub() : handleImport())
  }

  function added(work: TtsWork) {
    toast.success(t("tts.importOk"))
    setItems((prev) => [toListItem(work), ...prev.filter((w) => w.id !== work.id)])
    setImportOpen(false)
  }

  async function handleImport() {
    if (!title.trim() || !text.trim()) {
      toast.error(t("tts.importNeedFields"))
      return
    }
    setSaving(true)
    try {
      const work = await ttsApi.importTxt({ title: title.trim(), author: author.trim(), lang, text })
      setTitle("")
      setAuthor("")
      setText("")
      added(work)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  async function handleEpub() {
    if (!epubFile) {
      toast.error(t("tts.importEpubNeedFile"))
      return
    }
    setSaving(true)
    try {
      const work = await ttsApi.importEpub(epubFile, lang)
      setEpubFile(null)
      setFileInputKey((k) => k + 1)
      added(work)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  const addButton = (
    <Button type="button" onClick={() => setImportOpen(true)}>
      <Plus aria-hidden />
      {t("tts.addBook")}
    </Button>
  )

  return (
    <PageShell>
      <PageHeader
        eyebrow={t("tts.eyebrow")}
        stage="listen"
        title={t("tts.title")}
        description={t("tts.libraryHint")}
        meta={
          items.length > 0 ? (
            <span className="font-mono tabular-nums">{t("tts.libraryCount", { count: items.length })}</span>
          ) : null
        }
        primaryAction={addButton}
      />

      {loadError ? <p className="text-sm text-destructive">{loadError}</p> : null}

      {loading && items.length === 0 ? (
        <div className="grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6" aria-busy>
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="space-y-2.5">
              <div className="skeleton-shimmer aspect-[2/3] rounded-[6px_12px_12px_6px]" />
              <div className="skeleton-shimmer h-4 w-3/4 rounded" />
              <div className="skeleton-shimmer h-3 w-1/2 rounded" />
            </div>
          ))}
        </div>
      ) : items.length === 0 && !loadError ? (
        <div className="rounded-2xl border border-border bg-card">
          <EmptyState icon={Headphones} tone="listen" title={t("tts.empty")} hint={t("tts.emptyHint")} action={addButton} />
        </div>
      ) : (
        <ul className="stagger grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          {items.map((w) => {
            const status = w.latest_status ?? null
            const running = status === "running" || status === "queued"
            const total = w.latest_total ?? 0
            const done = w.latest_done ?? 0
            return (
              <li key={w.id} className="min-w-0">
                <Link
                  to={`/tts/${w.id}`}
                  className="group block rounded-xl focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"
                >
                  <BookCover title={w.title} subtitle={w.author || w.lang} />
                  <p className="mt-3 line-clamp-2 text-[15px] leading-snug font-semibold group-hover:underline">
                    {w.title}
                  </p>
                  <p className="mt-0.5 truncate text-[13px] text-muted-foreground">
                    {[w.author, w.lang].filter(Boolean).join(" · ")}
                    <span className="font-mono tabular-nums">
                      {" "}
                      · {w.chapter_count} {t("tts.chaptersShort")}
                    </span>
                  </p>
                </Link>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {status ? (
                    <StatusPill status={status} />
                  ) : (
                    <StatusPill status="idle" label={t("tts.notRead")} />
                  )}
                  {total > 0 ? (
                    <span className="font-mono text-xs text-muted-foreground tabular-nums">
                      {done}/{total}
                    </span>
                  ) : null}
                </div>
                {total > 0 && status !== "completed" ? (
                  <Progress
                    className="mt-2"
                    size="sm"
                    tone="listen"
                    live={running}
                    value={(done / total) * 100}
                    label={t("tts.readyOf", { done, total })}
                  />
                ) : null}
              </li>
            )
          })}
        </ul>
      )}

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="sm:max-w-xl">
          <form onSubmit={handleSubmit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>{t("tts.importTitle")}</DialogTitle>
              <DialogDescription>
                {importKind === "txt" ? t("tts.importHint") : t("tts.importEpubHint")}
              </DialogDescription>
            </DialogHeader>
            <SegmentedTabs
              value={importKind}
              onChange={setImportKind}
              items={[
                { value: "txt", label: t("tts.importKindTxt") },
                { value: "epub", label: t("tts.importKindEpub") },
              ]}
            />
            <div className="grid gap-3 sm:grid-cols-3">
              {importKind === "txt" ? (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="tts-title">{t("tts.bookTitle")}</Label>
                    <Input id="tts-title" value={title} onChange={(e) => setTitle(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="tts-author">{t("tts.author")}</Label>
                    <Input id="tts-author" value={author} onChange={(e) => setAuthor(e.target.value)} />
                  </div>
                </>
              ) : (
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="tts-epub">{t("tts.importEpubFile")}</Label>
                  <Input
                    key={fileInputKey}
                    id="tts-epub"
                    type="file"
                    accept=".epub,application/epub+zip"
                    onChange={(e) => setEpubFile(e.target.files?.[0] ?? null)}
                  />
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="tts-lang">{t("tts.lang")}</Label>
                <select id="tts-lang" className={selectClass} value={lang} onChange={(e) => setLang(e.target.value)}>
                  <option value="vi">vi</option>
                  <option value="zh">zh</option>
                  <option value="en">en</option>
                </select>
              </div>
            </div>
            {importKind === "txt" ? (
              <Textarea
                className="min-h-36"
                value={text}
                aria-label={t("tts.textLabel")}
                placeholder={t("tts.textPlaceholder")}
                onChange={(e) => setText(e.target.value)}
              />
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setImportOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={saving || (importKind === "epub" && !epubFile)}>
                {saving ? t("common.saving") : importKind === "epub" ? t("tts.importEpubSubmit") : t("tts.importTxt")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  )
}
