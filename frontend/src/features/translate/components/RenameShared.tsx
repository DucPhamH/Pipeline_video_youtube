/** Mảnh dùng chung cho bảng duyệt tên (glossary) và bảng đổi vỏ (skin map):
 * hộp xem trước / áp dụng thay thế, lịch sử batch + hoàn tác, chọn AI. */
import { Fragment, type ReactNode } from "react"
import { History, Loader2 } from "lucide-react"
import { EmptyState } from "@/components/EmptyState"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useT } from "@/i18n"
import { useConfirm } from "@/components/useConfirm"
import { translateApi } from "../api"
import { renameErrorText } from "../renameUtils"
import type { AiProvider, RenameBatch, RenameResult } from "../types"


function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/** Tô sáng mọi lần xuất hiện của `terms` trong `text`. */
export function HighlightedText({ text, terms, tone }: { text: string; terms: string[]; tone: "old" | "new" }) {
  const list = [...new Set(terms.filter((x) => x.trim()))].sort((a, b) => b.length - a.length)
  if (list.length === 0) return <>{text}</>
  const re = new RegExp(`(${list.map(escapeRe).join("|")})`, "g")
  const parts = text.split(re)
  const cls =
    tone === "old"
      ? "rounded-sm bg-danger-soft px-0.5 text-danger line-through decoration-danger/50"
      : "rounded-sm bg-success-soft px-0.5 font-medium text-success"
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <mark key={i} className={cls}>
            {p}
          </mark>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={className ?? "size-3.5 animate-spin"} aria-hidden />
}

type PreviewProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  preview: RenameResult | null
  loading: boolean
  applying: boolean
  /** Danh sách variant có thể chọn (bảng tên); bỏ trống = không hiện checkbox. */
  variants?: { id: number; label: string }[]
  selectedVariantIds?: number[]
  onSelectedVariantsChange?: (ids: number[]) => void
  onApply: () => void
}

/** Hộp "Xem trước thay đổi": số lần thay theo từng mục + mẫu trước/sau. */
export function RenamePreviewDialog({
  open,
  onOpenChange,
  title,
  preview,
  loading,
  applying,
  variants,
  selectedVariantIds = [],
  onSelectedVariantsChange,
  onApply,
}: PreviewProps) {
  const t = useT()
  const oldTerms = preview?.per_term.map((p) => p.old_target) ?? []
  const newTerms = preview?.per_term.map((p) => p.new_target) ?? []
  const noVariant = variants != null && variants.length > 0 && selectedVariantIds.length === 0

  return (
    <Dialog open={open} onOpenChange={(o) => !applying && onOpenChange(o)}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{t("translate.renamePreviewHint")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {variants && variants.length > 0 ? (
            <fieldset className="space-y-1.5">
              <legend className="text-xs font-medium text-muted-foreground">{t("translate.renameVariants")}</legend>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {variants.map((v) => (
                  <label key={v.id} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      disabled={loading || applying}
                      checked={selectedVariantIds.includes(v.id)}
                      onChange={(e) =>
                        onSelectedVariantsChange?.(
                          e.target.checked
                            ? [...selectedVariantIds, v.id]
                            : selectedVariantIds.filter((x) => x !== v.id),
                        )
                      }
                    />
                    {v.label}
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}

          {loading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Spinner /> {t("translate.renamePreviewLoading")}
            </p>
          ) : preview ? (
            <>
              <p className="text-sm">
                {t("translate.renameTotal", { count: preview.total_replacements })}
              </p>
              <div className="overflow-x-auto rounded-xl border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted text-xs font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                    <tr>
                      <th className="px-3 py-2 text-left">{t("translate.renameOld")}</th>
                      <th className="px-3 py-2 text-left">{t("translate.renameNew")}</th>
                      <th className="px-3 py-2 text-right">{t("translate.renameSegments")}</th>
                      <th className="px-3 py-2 text-right">{t("translate.renameReplacements")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {preview.per_term.map((p, i) => (
                      <tr key={p.term_id ?? p.row_id ?? i} className="transition-colors hover:bg-muted/50">
                        <td className="px-3 py-2">{p.old_target || "—"}</td>
                        <td className="px-3 py-2 font-medium">{p.new_target}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums">{p.segments}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums">{p.replacements}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {preview.samples.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">{t("translate.renameSamples")}</p>
                  <ul className="max-h-[40vh] space-y-2 overflow-y-auto">
                    {preview.samples.map((s, i) => (
                      <li key={`${s.segment_id}-${i}`} className="rounded-xl border border-border p-3 text-[13px]">
                        <p className="mb-1 font-medium text-muted-foreground">
                          #{s.chapter_index} {s.title || ""} · {t("translate.variantShort", { id: s.variant_id })}
                        </p>
                        <p className="leading-relaxed">
                          <span className="mr-1 text-muted-foreground">{t("translate.renameBefore")}:</span>
                          <HighlightedText text={s.before} terms={oldTerms} tone="old" />
                        </p>
                        <p className="mt-1 leading-relaxed">
                          <span className="mr-1 text-muted-foreground">{t("translate.renameAfter")}:</span>
                          <HighlightedText text={s.after} terms={newTerms} tone="new" />
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">{t("translate.renameNoSamples")}</p>
              )}
            </>
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" disabled={applying} onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button type="button" disabled={loading || applying || !preview || noVariant} onClick={onApply}>
            {applying ? <Spinner /> : null}
            {t("translate.renameApply")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


/** Lịch sử batch thay thế (tên + đổi vỏ) với nút Hoàn tác. */
export function RenameHistory({
  workId,
  batches,
  variantLabel,
  onUndone,
}: {
  workId: number
  batches: RenameBatch[]
  variantLabel: (variantId: number) => string
  onUndone: () => void
}) {
  const t = useT()
  const [confirm, confirmDialog] = useConfirm()

  async function undo(b: RenameBatch) {
    const ok = await confirm({
      title: t("translate.renameUndoTitle"),
      description: t("translate.renameUndoConfirm", { segments: b.segments }),
      confirmLabel: t("translate.renameUndo"),
    })
    if (!ok) return
    try {
      const r = await translateApi.undoRenameBatch(workId, b.id)
      toast.success(t("translate.renameUndone", { restored: r.restored, skipped: r.skipped }))
      onUndone()
    } catch (err) {
      toast.error(renameErrorText(err, t))
    }
  }

  return (
    <>
      {batches.length === 0 ? (
        <EmptyState icon={History} tone="neutral" compact title={t("translate.renameHistoryEmpty")} />
      ) : (
        <ul className="stagger -mx-2 divide-y divide-border text-sm">
          {batches.map((b) => (
            <li
              key={b.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg px-2 py-2.5 transition-colors hover:bg-muted/50"
            >
              <div className="min-w-0">
                <p className="text-[13px] text-muted-foreground">
                  {formatTime(b.created_at)} ·{" "}
                  {b.kind === "skin_map" ? t("translate.skinMapTitle") : t("translate.namesTitle")}
                  {b.variant_id != null ? ` · ${variantLabel(b.variant_id)}` : ""} ·{" "}
                  {t("translate.renameSegmentsCount", { count: b.segments })}
                </p>
                <p className="truncate">
                  {b.changes
                    .slice(0, 6)
                    .map((c) => `${c.old} → ${c.new}`)
                    .join(" · ")}
                  {b.changes.length > 6 ? ` · +${b.changes.length - 6}` : ""}
                </p>
              </div>
              <Button type="button" size="sm" variant="outline" onClick={() => void undo(b)}>
                {t("translate.renameUndo")}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {confirmDialog}
    </>
  )
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

/** Chọn 1 AI đã lưu (Settings) cho tác vụ LLM ngắn: trích tên / sinh skin map. */
export function AiProviderSelect({
  id,
  providers,
  value,
  onChange,
  disabled,
}: {
  id?: string
  providers: AiProvider[]
  value: number | null
  onChange: (id: number | null) => void
  disabled?: boolean
}) {
  const t = useT()
  return (
    <select
      id={id}
      aria-label={t("translate.ai")}
      disabled={disabled}
      className="h-9 max-w-full rounded-lg border border-input bg-card px-2.5 text-sm"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">{t("translate.aiDefaultOption")}</option>
      {[...providers]
        .sort((a, b) => Number(a.kind === "mock") - Number(b.kind === "mock"))
        .map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
            {p.kind === "mock" ? ` ${t("translate.mockSuffix")}` : ""}
          </option>
        ))}
    </select>
  )
}


export function SubHeading({ children }: { children: ReactNode }) {
  return <h3 className="text-sm font-medium">{children}</h3>
}
