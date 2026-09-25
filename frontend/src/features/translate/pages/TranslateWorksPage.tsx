import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { PageHeader, PageShell, SectionCard, Toolbar } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { translateApi } from "../api"
import type { Inbox, Work } from "../types"

export function TranslateWorksPage() {
  const t = useT()
  const [items, setItems] = useState<Work[]>([])
  const [inbox, setInbox] = useState<Inbox | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [author, setAuthor] = useState("")
  const [langSrc, setLangSrc] = useState("zh")
  const [text, setText] = useState("")
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [search, setSearch] = useState("")

  const filteredItems = items.filter((w) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return w.title.toLowerCase().includes(q) || w.author.toLowerCase().includes(q)
  })

  function load() {
    translateApi
      .listWorks()
      .then((r) => setItems(r.items))
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("app.unknownError")),
      )
    translateApi
      .getInbox()
      .then(setInbox)
      .catch(() => setInbox(null))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
      toast.success(t("translate.importOk"))
      setImportOpen(false)
      setTitle("")
      setAuthor("")
      setText("")
      setItems((prev) => [work, ...prev.filter((w) => w.id !== work.id)])
      const next = await translateApi.getInbox().catch(() => null)
      if (next) setInbox(next)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <PageShell>
        <p className="text-sm text-destructive">{loadError}</p>
        <Button type="button" variant="outline" className="mt-3" onClick={load}>
          {t("translate.reload")}
        </Button>
      </PageShell>
    )
  }

  async function handleDeleteWork(id: number) {
    if (!window.confirm(t("translate.deleteWorkConfirm"))) return
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

  function inboxBucket(title: string, rows: Inbox["running"]) {
    if (!rows.length) return null
    return (
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">{title}</p>
        <ul className="divide-y divide-border text-sm">
          {rows.map((row) => (
            <li key={`${row.work_id}-${row.variant_id}`}>
              <Link
                to={`/translate/${row.work_id}`}
                className="flex items-baseline justify-between gap-2 py-2 hover:text-primary"
              >
                <span className="truncate">
                  {row.work_title} · #{row.variant_id} {row.mode}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {row.job_status || row.variant_status}
                  {row.unreviewed ? ` · ${row.unreviewed}` : ""}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <PageShell>
      <PageHeader
        title={t("translate.title")}
        description={t("translate.subtitle")}
        actions={
          <Toolbar>
            <Link
              to="/translate/settings"
              className="inline-flex h-8 items-center rounded-lg border border-border bg-card px-2.5 text-sm font-medium hover:bg-muted"
            >
              {t("translate.settings")}
            </Link>
            <Button type="button" onClick={() => setImportOpen((v) => !v)}>
              {t("translate.importTxt")}
            </Button>
          </Toolbar>
        }
      />

      {importOpen ? (
        <SectionCard title={t("translate.importTxt")} description={t("translate.importHint")}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="tr-title">{t("translate.fieldTitle")}</Label>
              <Input id="tr-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tr-author">{t("translate.fieldAuthor")}</Label>
              <Input id="tr-author" value={author} onChange={(e) => setAuthor(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tr-lang">{t("translate.fieldLangSrc")}</Label>
              <Input id="tr-lang" value={langSrc} onChange={(e) => setLangSrc(e.target.value)} />
            </div>
          </div>
          <div className="mt-3 space-y-1.5">
            <Label htmlFor="tr-text">{t("translate.fieldText")}</Label>
            <Textarea
              id="tr-text"
              rows={10}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="font-mono text-xs"
            />
          </div>
          <div className="mt-3 flex gap-2">
            <Button type="button" disabled={saving} onClick={handleImport}>
              {saving ? t("common.saving") : t("translate.importSubmit")}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setImportOpen(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </SectionCard>
      ) : null}

      {inbox &&
      (inbox.running.length || inbox.needs_review.length || inbox.ready_export.length) ? (
        <SectionCard title={t("translate.inbox")} description={t("translate.inboxHint")}>
          <div className="grid gap-4 md:grid-cols-3">
            {inboxBucket(t("translate.inboxRunning"), inbox.running)}
            {inboxBucket(t("translate.inboxReview"), inbox.needs_review)}
            {inboxBucket(t("translate.inboxReady"), inbox.ready_export)}
          </div>
        </SectionCard>
      ) : null}

      <SectionCard title={t("translate.library")}>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("translate.empty")}</p>
        ) : (
          <>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("translate.searchWorks")}
              className="mb-3 h-9"
            />
            {filteredItems.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("translate.segmentsFilterEmpty")}</p>
            ) : (
              <ul className="divide-y divide-border">
                {filteredItems.map((w) => (
                  <li key={w.id} className="flex items-center gap-2 py-1">
                    <Link
                      to={`/translate/${w.id}`}
                      className="flex min-w-0 flex-1 items-baseline justify-between gap-3 py-2 transition-colors hover:text-primary"
                    >
                      <span className="min-w-0 truncate">
                        <span className="font-heading text-base">{w.title}</span>
                        {w.missing_cleaned > 0 || w.unreviewed_chapters > 0 ? (
                          <span
                            className="ml-2 rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300"
                            title={t("translate.qualityGateHint")}
                          >
                            !
                          </span>
                        ) : null}
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {w.lang_src}→{w.lang_tgt} · {w.chapters.length} ch · {w.source_type}
                      </span>
                    </Link>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={deletingId === w.id}
                      onClick={() => void handleDeleteWork(w.id)}
                    >
                      {t("common.confirmDelete")}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </SectionCard>
    </PageShell>
  )
}
