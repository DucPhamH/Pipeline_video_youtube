import { useLayoutEffect, useRef } from "react"
import { BookOpenText, ChevronLeft, ChevronRight, Flag, RotateCcw, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/EmptyState"
import { StatusPill } from "@/components/StatusPill"
import { useT } from "@/i18n"
import { friendlyError, qaFlagLabel } from "../errorText"
import { useStatusLabels } from "../hooks/useStatusLabels"
import type { SegmentDetail } from "../types"

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)

export function ReviewPane({
  segment,
  title,
  langSrc,
  langTgt,
  value,
  onChange,
  dirty,
  saving,
  onSave,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
  onClose,
  onRetranslateFlagged,
  retranslateDisabled,
}: {
  segment: SegmentDetail | null
  title: string
  langSrc: string
  langTgt: string
  value: string
  onChange: (v: string) => void
  dirty: boolean
  saving: boolean
  onSave: () => void
  onPrev: () => void
  onNext: () => void
  hasPrev: boolean
  hasNext: boolean
  onClose: () => void
  onRetranslateFlagged: (flag?: string) => void
  retranslateDisabled: boolean
}) {
  const t = useT()
  const { segmentStatusLabel } = useStatusLabels()
  const areaRef = useRef<HTMLTextAreaElement>(null)

  // Tự giãn textarea theo nội dung (cột cuộn thay vì textarea cuộn).
  useLayoutEffect(() => {
    const el = areaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }, [value, segment?.id])

  if (!segment) {
    return (
      <div className="flex min-h-[20rem] flex-1 items-center justify-center">
        <EmptyState
          icon={BookOpenText}
          tone="translate"
          title={t("translate.job.pickChapter")}
          hint={t("translate.job.pickChapterHint")}
        />
      </div>
    )
  }

  const flags = segment.qa_flags ?? []
  const doneLike = segment.status === "done" || segment.status === "skipped_cache"
  const langName = (code: string) => {
    const key = `lang.${code}`
    const v = t(key)
    return v === key ? code.toUpperCase() : v
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border bg-card px-5 py-3.5 sm:px-7">
        <span className="font-mono text-xs text-muted-foreground tabular-nums">#{segment.chapter_index}</span>
        <h2 className="min-w-0 flex-1 truncate font-display text-[22px] leading-tight font-semibold">{title}</h2>
        <StatusPill
          status={segment.status}
          label={segmentStatusLabel(segment.status)}
          tone={doneLike ? "success" : undefined}
        />
        <div className="ml-auto flex items-center gap-1.5">
          <Button type="button" variant="outline" size="sm" disabled={!hasPrev} onClick={onPrev}>
            <ChevronLeft aria-hidden />
            {t("common.prev")}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={!hasNext} onClick={onNext}>
            {t("common.next")}
            <ChevronRight aria-hidden />
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={saving}
            onClick={onSave}
            title={isMac ? "⌘S" : "Ctrl+S"}
          >
            {saving ? t("common.saving") : t("translate.job.save")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label={t("translate.job.close")}
            title={t("translate.job.close")}
          >
            <X aria-hidden />
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-2">
        <section className="min-h-0 overflow-y-auto border-b border-border px-5 py-6 sm:px-7 lg:border-r lg:border-b-0">
          <h3 className="mb-3.5 text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
            {t("translate.job.source", { lang: langName(langSrc) })}
          </h3>
          <div className="text-[16px] leading-[1.8] whitespace-pre-wrap text-foreground/85">{segment.source_text}</div>
        </section>

        <section className="flex min-h-0 flex-col overflow-y-auto bg-card/60 px-5 py-6 sm:px-7">
          <h3 className="mb-3.5 flex items-center gap-2 text-xs font-semibold tracking-[0.08em] text-accent-foreground uppercase">
            <label htmlFor="seg-out">{t("translate.job.translation", { lang: langName(langTgt) })}</label>
            <span className="ml-auto text-xs font-medium tracking-normal normal-case text-muted-foreground">
              {dirty ? t("translate.job.unsaved") : segment.reviewed ? `✓ ${t("translate.reviewed")}` : null}
            </span>
          </h3>
          <textarea
            id="seg-out"
            ref={areaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={t("translate.job.noOutput")}
            spellCheck={false}
            className="-mx-2 block min-h-48 w-[calc(100%+1rem)] resize-none overflow-hidden rounded-lg border border-transparent bg-transparent px-2 py-1 text-[16px] leading-[1.8] text-foreground transition-colors outline-none placeholder:text-muted-foreground hover:border-border focus-visible:border-ring focus-visible:bg-card focus-visible:ring-3 focus-visible:ring-ring/30"
          />

          {segment.error || flags.length > 0 ? (
            <div className="mt-auto space-y-2 pt-6">
              {segment.error ? (
                <p className="rounded-xl border border-danger/25 bg-danger-soft px-3.5 py-3 text-[13px] text-danger">
                  {friendlyError(segment.error, t)}
                </p>
              ) : null}
              {flags.length > 0 ? (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-danger/25 bg-danger-soft px-3.5 py-3 text-[13px] text-danger">
                  <Flag className="size-4 shrink-0" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="font-semibold">{t("translate.qaFlagsLabel")}:</span>{" "}
                    {flags.map((f) => qaFlagLabel(f, t)).join(", ")}
                    <span className="mt-0.5 block text-xs opacity-80">{t("translate.job.retranslateHint")}</span>
                  </span>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    disabled={retranslateDisabled}
                    onClick={() => onRetranslateFlagged(flags.length === 1 ? flags[0] : undefined)}
                  >
                    <RotateCcw aria-hidden />
                    {t("translate.job.retranslateFlagged")}
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}
