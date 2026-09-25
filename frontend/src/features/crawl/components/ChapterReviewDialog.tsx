import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import { crawlApi } from "../api"

type ViewMode = "edit" | "compare"

export function ChapterReviewDialog({
  chapterId,
  chapterTitle,
  open,
  onOpenChange,
  onSaved,
  hasNext = false,
  onSaveAndNext,
}: {
  chapterId: number
  chapterTitle: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
  hasNext?: boolean
  onSaveAndNext?: () => void | Promise<void>
}) {
  const t = useT()
  const [content, setContent] = useState("")
  const [rawContent, setRawContent] = useState("")
  const [reviewed, setReviewed] = useState(false)
  const [hasCleaned, setHasCleaned] = useState(false)
  const [contentSource, setContentSource] = useState<"raw" | "cleaned">("raw")
  const [viewMode, setViewMode] = useState<ViewMode>("edit")
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savingNext, setSavingNext] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setLoadError(null)
    crawlApi
      .getChapterContent(chapterId)
      .then((data) => {
        setContent(data.content ?? "")
        setRawContent(data.raw_content ?? data.content ?? "")
        setReviewed(data.reviewed)
        const cleaned = Boolean(data.has_cleaned)
        setHasCleaned(cleaned)
        setContentSource(data.content_source === "cleaned" ? "cleaned" : "raw")
        setViewMode(cleaned ? "compare" : "edit")
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("app.unknownError")))
      .finally(() => setLoading(false))
  }, [open, chapterId, t])

  async function persist(): Promise<boolean> {
    try {
      const result = await crawlApi.updateChapterContent(chapterId, content)
      setReviewed(result.reviewed)
      setHasCleaned(Boolean(result.has_cleaned))
      setContentSource(result.content_source === "cleaned" ? "cleaned" : "raw")
      if (result.has_cleaned) {
        setContent(result.content ?? content)
      }
      toast.success(result.has_cleaned ? t("review.savedCleaned") : t("review.savedRaw"))
      onSaved()
      return true
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
      return false
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      await persist()
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveAndNext() {
    if (!onSaveAndNext) return
    setSavingNext(true)
    try {
      const ok = await persist()
      if (ok) await onSaveAndNext()
    } finally {
      setSavingNext(false)
    }
  }

  function resetToRaw() {
    setLoading(true)
    crawlApi
      .discardChapterCleaned(chapterId)
      .then((data) => {
        const raw = data.raw_content ?? data.content ?? ""
        setContent(raw)
        setRawContent(raw)
        setHasCleaned(false)
        setContentSource("raw")
        setViewMode("edit")
        setReviewed(data.reviewed)
        toast.message(t("review.restored"))
        onSaved()
      })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")))
      .finally(() => setLoading(false))
  }

  const busy = loading || saving || savingNext || !!loadError
  const wide = viewMode === "compare" && hasCleaned

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={`flex max-h-[90vh] flex-col overflow-y-auto ${wide ? "sm:max-w-5xl" : "sm:max-w-2xl"}`}
      >
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {chapterTitle}
            {hasCleaned && <Badge variant="outline">{t("review.smoothed")}</Badge>}
            {reviewed && <Badge variant="secondary">{t("review.reviewed")}</Badge>}
          </DialogTitle>
          <DialogDescription>
            {hasCleaned ? t("review.descCompare") : t("review.descRaw")}
          </DialogDescription>
        </DialogHeader>

        {hasCleaned && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant={viewMode === "compare" ? "default" : "outline"}
              onClick={() => setViewMode("compare")}
            >
              {t("review.compare")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant={viewMode === "edit" ? "default" : "outline"}
              onClick={() => setViewMode("edit")}
            >
              {t("review.editOnly")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={resetToRaw}
              disabled={loading}
              title={t("review.restoreTitle")}
            >
              {t("review.restoreRaw")}
            </Button>
          </div>
        )}

        {loadError && <p className="text-sm text-destructive">{loadError}</p>}
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t("review.loading")}</p>
        ) : (
          !loadError &&
          (viewMode === "compare" && hasCleaned ? (
            <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-2">
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">{t("review.rawLabel")}</p>
                <Textarea
                  value={rawContent}
                  readOnly
                  rows={16}
                  className="field-sizing-fixed h-[50vh] resize-y overflow-y-auto bg-muted/40 font-mono text-sm"
                />
              </div>
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">
                  {t("review.cleanedLabel", { source: contentSource })}
                </p>
                <Textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={16}
                  className="field-sizing-fixed h-[50vh] resize-y overflow-y-auto font-mono text-sm"
                  placeholder={t("review.placeholderCleaned")}
                />
              </div>
            </div>
          ) : (
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={16}
              className="field-sizing-fixed h-[50vh] resize-y overflow-y-auto font-mono text-sm"
              placeholder={t("review.placeholderRaw")}
            />
          ))
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.close")}
          </Button>
          <Button onClick={() => void handleSave()} disabled={busy}>
            {saving ? t("review.saving") : t("review.save")}
          </Button>
          {onSaveAndNext ? (
            <Button
              variant="secondary"
              onClick={() => void handleSaveAndNext()}
              disabled={busy || !hasNext}
              title={!hasNext ? t("review.noMore") : undefined}
            >
              {savingNext ? t("review.savingNext") : t("review.saveAndNext")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
