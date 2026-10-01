/** Bảng "đổi vỏ" (skin map) của 1 variant reskin: gốc → thay thế, khoá dòng,
 * sinh bằng AI, xem trước + áp dụng vào chương đã dịch (giống bảng tên). */
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { useConfirm } from "@/components/useConfirm"
import { translateApi } from "../api"
import { AiProviderSelect, RenamePreviewDialog, Spinner } from "./RenameShared"
import { NAME_KINDS, renameErrorText, toastApplied, useNameKindLabel } from "../renameUtils"
import type { AiProvider, RenameResult, SkinMapRow, Variant } from "../types"
import { ListSkeleton } from "@/components/Skeleton"
import { EmptyState } from "@/components/EmptyState"
import { Lock, LockOpen, Plus, Shirt, Sparkles, Trash2 } from "lucide-react"

export function SkinMapEditor({
  workId,
  variant,
  providers,
  providerId,
  onProviderChange,
  onApplied,
}: {
  workId: number
  variant: Variant
  providers: AiProvider[]
  providerId: number | null
  onProviderChange: (id: number | null) => void
  onApplied: () => void
}) {
  const t = useT()
  const kindLabel = useNameKindLabel()
  const [confirm, confirmDialog] = useConfirm()
  const variantId = variant.id

  const [rows, setRows] = useState<SkinMapRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [generating, setGenerating] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [saving, setSaving] = useState(false)

  const [newOrig, setNewOrig] = useState("")
  const [newRepl, setNewRepl] = useState("")
  const [newKind, setNewKind] = useState("")

  const [previewOpen, setPreviewOpen] = useState(false)
  const [preview, setPreview] = useState<RenameResult | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const inputsRef = useRef<(HTMLInputElement | null)[]>([])

  const hasOutput = variant.latest_job_id != null

  const load = useCallback(async () => {
    try {
      setRows(await translateApi.listSkinMap(variantId))
      setLoadError(null)
    } catch (err) {
      setLoadError(renameErrorText(err, t))
    } finally {
      setLoading(false)
    }
  }, [variantId, t])

  // Đổi variant → NamesTab remount theo key, nên chỉ cần tải 1 lần.
  useEffect(() => {
    void load()
  }, [load])

  function draftState(r: SkinMapRow): "clean" | "dirty" | "empty" {
    const d = drafts[r.id]
    if (d === undefined) return "clean"
    const v = d.trim()
    if (v === r.replacement.trim()) return "clean"
    return v ? "dirty" : "empty"
  }
  const dirty = rows.filter((r) => draftState(r) === "dirty")
  const hasEmpty = rows.some((r) => draftState(r) === "empty")
  const changes = () => dirty.map((r) => ({ row_id: r.id, new_replacement: drafts[r.id].trim() }))

  async function handleGenerate() {
    if (overwrite && rows.length > 0) {
      const ok = await confirm({
        title: t("translate.skinMapGenerate"),
        description: t("translate.skinMapOverwriteConfirm", { count: rows.filter((r) => !r.locked).length }),
        confirmLabel: t("translate.skinMapGenerate"),
      })
      if (!ok) return
    }
    setGenerating(true)
    try {
      const out = await translateApi.generateSkinMap(variantId, {
        provider_id: providerId ?? undefined,
        overwrite,
      })
      setRows(out)
      setDrafts({})
      toast.success(t("translate.skinMapGenerated", { count: out.length }))
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setGenerating(false)
    }
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (!newOrig.trim() || !newRepl.trim()) return
    try {
      const row = await translateApi.addSkinMapRow(variantId, {
        original: newOrig.trim(),
        replacement: newRepl.trim(),
        kind: newKind || undefined,
      })
      setRows((r) => [...r, row])
      setNewOrig("")
      setNewRepl("")
    } catch (err) {
      toast.error(renameErrorText(err, t))
    }
  }

  async function patchRow(r: SkinMapRow, body: { kind?: string; locked?: boolean }) {
    setRows((cur) => cur.map((x) => (x.id === r.id ? { ...x, ...body } : x)))
    try {
      const updated = await translateApi.updateSkinMapRow(variantId, r.id, body)
      setRows((cur) => cur.map((x) => (x.id === r.id ? updated : x)))
    } catch (err) {
      setRows((cur) => cur.map((x) => (x.id === r.id ? r : x)))
      toast.error(renameErrorText(err, t))
    }
  }

  async function removeRow(r: SkinMapRow) {
    const ok = await confirm({
      title: t("common.deleteTitle"),
      description: t("translate.skinMapDeleteConfirm", { term: r.original }),
    })
    if (!ok) return
    try {
      await translateApi.deleteSkinMapRow(variantId, r.id)
      setRows((cur) => cur.filter((x) => x.id !== r.id))
    } catch (err) {
      toast.error(renameErrorText(err, t))
    }
  }

  async function openPreview() {
    setPreview(null)
    setPreviewOpen(true)
    setPreviewLoading(true)
    try {
      setPreview(await translateApi.applySkinMap(variantId, { changes: changes(), dry_run: true }))
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setPreviewLoading(false)
    }
  }

  async function handleApply() {
    const ok = await confirm({
      title: t("translate.renameApplyTitle"),
      description: t("translate.renameApplyConfirm", { count: preview?.total_replacements ?? 0 }),
      confirmLabel: t("translate.renameApply"),
      destructive: false,
    })
    if (!ok) return
    setApplying(true)
    try {
      const r = await translateApi.applySkinMap(variantId, { changes: changes(), dry_run: false })
      setPreviewOpen(false)
      setDrafts({})
      toastApplied(t, workId, r, () => {
        void load()
        onApplied()
      })
      await load()
      onApplied()
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setApplying(false)
    }
  }

  /** Chưa dịch chương nào → chỉ lưu bảng (PUT từng dòng). */
  async function handleSaveOnly() {
    setSaving(true)
    try {
      for (const r of dirty) {
        const updated = await translateApi.updateSkinMapRow(variantId, r.id, { replacement: drafts[r.id].trim() })
        setRows((cur) => cur.map((x) => (x.id === r.id ? updated : x)))
      }
      setDrafts({})
      toast.success(t("translate.namesSaved", { count: dirty.length }))
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="sticky top-14 z-20 flex flex-wrap items-center gap-2 rounded-xl bg-muted/80 p-2.5 backdrop-blur lg:top-0">
        <Sparkles className="ml-1 size-4 text-info" aria-hidden />
        <AiProviderSelect providers={providers} value={providerId} onChange={onProviderChange} disabled={generating} />
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" className="size-4 accent-primary" checked={overwrite} disabled={generating} onChange={(e) => setOverwrite(e.target.checked)} />
          {t("translate.skinMapOverwrite")}
        </label>
        <Button type="button" size="sm" variant="outline" disabled={generating} onClick={() => void handleGenerate()}>
          {generating ? <Spinner /> : null}
          {generating ? t("translate.skinMapGenerating") : t("translate.skinMapGenerate")}
        </Button>
      </div>

      {loading ? (
        <ListSkeleton />
      ) : loadError ? (
        <p className="text-sm text-destructive">{loadError}</p>
      ) : rows.length === 0 ? (
        <EmptyState icon={Shirt} tone="neutral" compact title={t("translate.skinMapEmpty")} />
      ) : (
        <div className="max-h-[50vh] overflow-auto rounded-xl border border-border">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="sticky top-0 z-10 bg-muted text-xs font-semibold tracking-[0.06em] text-muted-foreground uppercase">
              <tr>
                <th className="px-3 py-2 text-left">{t("translate.skinMapOriginal")}</th>
                <th className="px-3 py-2 text-left">{t("translate.skinMapReplacement")}</th>
                <th className="px-3 py-2 text-left">{t("translate.nameKind")}</th>
                <th className="px-3 py-2 text-left">{t("translate.skinMapLocked")}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((r, i) => {
                const st = draftState(r)
                return (
                  <tr
                    key={r.id}
                    className={cn(
                      "transition-colors hover:bg-muted/50",
                      st === "dirty" && "bg-warning-soft hover:bg-warning-soft",
                      st === "empty" && "bg-danger-soft hover:bg-danger-soft",
                    )}
                  >
                    <td className="px-3 py-2 font-medium">{r.original}</td>
                    <td className="px-3 py-2">
                      <span className="mr-1 text-[13px] text-muted-foreground">{r.replacement || "—"} →</span>
                      <Input
                        ref={(el) => {
                          inputsRef.current[i] = el
                        }}
                        className="mt-1 min-w-36"
                        aria-label={t("translate.namesNewTargetFor", { term: r.original })}
                        aria-invalid={st === "empty" || undefined}
                        value={drafts[r.id] ?? r.replacement}
                        onChange={(e) => {
                          const v = e.target.value
                          setDrafts((d) => ({ ...d, [r.id]: v }))
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault()
                            const next = inputsRef.current[i + (e.shiftKey ? -1 : 1)]
                            next?.focus()
                            next?.select()
                          }
                        }}
                      />
                      {st === "empty" ? (
                        <p className="mt-0.5 text-xs text-destructive">{t("translate.namesEmptyBlocked")}</p>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <select
                        aria-label={t("translate.nameKind")}
                        className="h-9 rounded-lg border border-input bg-card px-2 text-[13px]"
                        value={r.kind || ""}
                        onChange={(e) => void patchRow(r, { kind: e.target.value })}
                      >
                        {r.kind && !(NAME_KINDS as string[]).includes(r.kind) ? <option value={r.kind}>{r.kind}</option> : null}
                        {NAME_KINDS.map((k) => (
                          <option key={k || "none"} value={k}>
                            {kindLabel(k)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        aria-pressed={r.locked}
                        onClick={() => void patchRow(r, { locked: !r.locked })}
                        className={cn(
                          "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold transition-colors",
                          r.locked ? "bg-info-soft text-info" : "bg-muted text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {r.locked ? <Lock className="size-3.5" aria-hidden /> : <LockOpen className="size-3.5" aria-hidden />}
                        {r.locked ? t("translate.skinMapLockedHint") : t("translate.skinMapLocked")}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        aria-label={t("common.confirmDelete")}
                        onClick={() => void removeRow(r)}
                      >
                        <Trash2 className="text-muted-foreground" />
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <form
        className="grid gap-2 rounded-xl border border-dashed border-border p-3 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end"
        onSubmit={(e) => void handleAdd(e)}
      >
        <div className="space-y-1">
          <Label htmlFor={`sm-orig-${variantId}`}>{t("translate.skinMapOriginal")}</Label>
          <Input id={`sm-orig-${variantId}`} value={newOrig} onChange={(e) => setNewOrig(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`sm-repl-${variantId}`}>{t("translate.skinMapReplacement")}</Label>
          <Input id={`sm-repl-${variantId}`} value={newRepl} onChange={(e) => setNewRepl(e.target.value)} />
        </div>
        <select
          aria-label={t("translate.nameKind")}
          className="h-9 rounded-lg border border-input bg-card px-2 text-[13px]"
          value={newKind}
          onChange={(e) => setNewKind(e.target.value)}
        >
          {NAME_KINDS.map((k) => (
            <option key={k || "none"} value={k}>
              {kindLabel(k)}
            </option>
          ))}
        </select>
        <Button type="submit" variant="outline" disabled={!newOrig.trim() || !newRepl.trim()}>
          <Plus aria-hidden />
          {t("translate.skinMapAddRow")}
        </Button>
      </form>

      <div
        className={cn(
          "sticky bottom-0 z-20 flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 transition-colors",
          dirty.length > 0 ? "border-warning/30 bg-warning-soft" : "border-border bg-card",
        )}
      >
        <span className={cn("text-[13px]", dirty.length > 0 ? "font-medium text-warning" : "text-muted-foreground")}>
          {t("translate.namesDirtyCount", { count: dirty.length })}
          {hasEmpty ? ` · ${t("translate.namesEmptyBlocked")}` : ""}
        </span>
        {dirty.length > 0 ? (
          <Button type="button" size="sm" variant="ghost" onClick={() => setDrafts({})}>
            {t("translate.namesDiscard")}
          </Button>
        ) : null}
        <div className="ml-auto">
          {hasOutput ? (
            <Button type="button" size="sm" disabled={dirty.length === 0 || hasEmpty} onClick={() => void openPreview()}>
              {t("translate.renamePreview")}
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              disabled={dirty.length === 0 || hasEmpty || saving}
              onClick={() => void handleSaveOnly()}
            >
              {saving ? <Spinner /> : null}
              {t("translate.namesSaveOnly")}
            </Button>
          )}
        </div>
      </div>

      <RenamePreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        title={t("translate.skinMapPreviewTitle")}
        preview={preview}
        loading={previewLoading}
        applying={applying}
        onApply={() => void handleApply()}
      />
      {confirmDialog}
    </div>
  )
}
