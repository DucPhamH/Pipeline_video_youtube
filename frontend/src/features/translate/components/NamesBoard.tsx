/** Bảng duyệt tên của 1 work: lọc/tìm, sửa tên dịch mới, duyệt ứng viên,
 * trích tên bằng AI, xem trước + áp dụng đổi tên vào chương đã dịch. */
import { useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { StatusPill } from "@/components/StatusPill"
import { EmptyState } from "@/components/EmptyState"
import { Search, Sparkles, Trash2, Users } from "lucide-react"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { useConfirm } from "@/components/useConfirm"
import { SegmentedTabs } from "@/components/PageChrome"
import { translateApi } from "../api"
import { useModeLabel } from "./ModeParamsFields"
import { AiProviderSelect, RenamePreviewDialog, Spinner } from "./RenameShared"
import { NAME_KINDS, renameErrorText, toastApplied, useNameKindLabel } from "../renameUtils"
import type { AiProvider, NameItem, NameKind, RenameResult, Work } from "../types"

type StatusFilter = "all" | "candidate" | "approved"

export function NamesBoard({
  work,
  names,
  onNamesChange,
  reload,
  providers,
  providerId,
  onProviderChange,
  onApplied,
}: {
  work: Work
  names: NameItem[]
  onNamesChange: (updater: (cur: NameItem[]) => NameItem[]) => void
  reload: () => Promise<void>
  providers: AiProvider[]
  providerId: number | null
  onProviderChange: (id: number | null) => void
  /** Gọi sau khi áp dụng / hoàn tác — để tải lại lịch sử batch. */
  onApplied: () => void
}) {
  const t = useT()
  const modeLabel = useModeLabel()
  const kindLabel = useNameKindLabel()
  const [confirm, confirmDialog] = useConfirm()

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [kindFilter, setKindFilter] = useState<string>("__all__")
  const [search, setSearch] = useState("")
  /** term id → tên dịch mới đang gõ. */
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [extracting, setExtracting] = useState(false)
  const [approving, setApproving] = useState(false)

  const [previewOpen, setPreviewOpen] = useState(false)
  const [preview, setPreview] = useState<RenameResult | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [saving, setSaving] = useState(false)
  const outputVariants = useMemo(() => work.variants.filter((v) => v.latest_job_id != null), [work.variants])
  const [variantIds, setVariantIds] = useState<number[]>([])

  const inputsRef = useRef<(HTMLInputElement | null)[]>([])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return names.filter((n) => {
      if (statusFilter !== "all" && n.status !== statusFilter) return false
      if (kindFilter !== "__all__" && (n.kind || "") !== kindFilter) return false
      if (q) {
        const blob = `${n.source_term} ${n.target_term} ${drafts[n.id] ?? ""} ${n.notes}`.toLowerCase()
        if (!blob.includes(q)) return false
      }
      return true
    })
  }, [names, statusFilter, kindFilter, search, drafts])

  /** Draft khác tên hiện tại (sau trim) mới tính là thay đổi. */
  function draftState(n: NameItem): "clean" | "dirty" | "empty" {
    const d = drafts[n.id]
    if (d === undefined) return "clean"
    const v = d.trim()
    if (v === n.target_term.trim()) return "clean"
    return v ? "dirty" : "empty"
  }

  const dirty = names.filter((n) => draftState(n) === "dirty")
  const hasEmpty = names.some((n) => draftState(n) === "empty")
  const candidatesVisible = filtered.filter((n) => n.status === "candidate")
  const hasOutput = outputVariants.length > 0

  function changes() {
    return dirty.map((n) => ({ term_id: n.id, new_target: drafts[n.id].trim() }))
  }

  async function handleExtract() {
    if (names.length > 0) {
      const ok = await confirm({
        title: t("translate.namesExtractTitle"),
        description: t("translate.namesExtractAgainConfirm", { count: names.length }),
        confirmLabel: t("translate.namesExtract"),
        destructive: false,
      })
      if (!ok) return
    }
    setExtracting(true)
    try {
      const r = await translateApi.extractNames(work.id, { provider_id: providerId ?? undefined })
      toast.success(t("translate.namesExtracted", { count: r.added }))
      await reload()
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setExtracting(false)
    }
  }

  async function approve(ids: number[]) {
    if (ids.length === 0) return
    setApproving(true)
    try {
      const updated = await translateApi.approveNames(work.id, ids)
      const map = new Map(updated.map((u) => [u.id, u]))
      onNamesChange((cur) => cur.map((n) => map.get(n.id) ?? (ids.includes(n.id) ? { ...n, status: "approved" } : n)))
      toast.success(t("translate.namesApproved", { count: ids.length }))
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setApproving(false)
    }
  }

  async function changeKind(n: NameItem, kind: NameKind) {
    const prev = n.kind
    onNamesChange((cur) => cur.map((x) => (x.id === n.id ? { ...x, kind } : x)))
    try {
      await translateApi.updateGlossary(work.id, n.id, {
        source_term: n.source_term,
        target_term: n.target_term,
        protected: n.protected,
        notes: n.notes,
        kind,
        status: n.status,
      })
    } catch (err) {
      onNamesChange((cur) => cur.map((x) => (x.id === n.id ? { ...x, kind: prev } : x)))
      toast.error(renameErrorText(err, t))
    }
  }

  async function removeName(n: NameItem) {
    const ok = await confirm({
      title: t("common.deleteTitle"),
      description: t("translate.glossaryDeleteConfirm", { term: n.source_term }),
    })
    if (!ok) return
    try {
      await translateApi.deleteGlossary(work.id, n.id)
      onNamesChange((cur) => cur.filter((x) => x.id !== n.id))
    } catch (err) {
      toast.error(renameErrorText(err, t))
    }
  }

  async function runPreview(ids: number[]) {
    setPreviewLoading(true)
    try {
      setPreview(await translateApi.applyNames(work.id, { changes: changes(), variant_ids: ids, dry_run: true }))
    } catch (err) {
      setPreview(null)
      toast.error(renameErrorText(err, t))
    } finally {
      setPreviewLoading(false)
    }
  }

  function openPreview() {
    const ids = outputVariants.map((v) => v.id)
    setVariantIds(ids)
    setPreview(null)
    setPreviewOpen(true)
    void runPreview(ids)
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
      const r = await translateApi.applyNames(work.id, { changes: changes(), variant_ids: variantIds, dry_run: false })
      setPreviewOpen(false)
      setDrafts({})
      toastApplied(t, work.id, r, () => {
        void reload()
        onApplied()
      })
      await reload()
      onApplied()
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setApplying(false)
    }
  }

  /** Chưa có chương dịch nào → chỉ lưu tên mới vào glossary (không cần rewrite). */
  async function handleSaveOnly() {
    setSaving(true)
    try {
      for (const n of dirty) {
        const target = drafts[n.id].trim()
        await translateApi.updateGlossary(work.id, n.id, {
          source_term: n.source_term,
          target_term: target,
          protected: n.protected,
          notes: n.notes,
          kind: n.kind,
          status: n.status,
        })
        onNamesChange((cur) => cur.map((x) => (x.id === n.id ? { ...x, target_term: target } : x)))
      }
      setDrafts({})
      toast.success(t("translate.namesSaved", { count: dirty.length }))
    } catch (err) {
      toast.error(renameErrorText(err, t))
    } finally {
      setSaving(false)
    }
  }

  function variantLabel(variantId: number, mode: string) {
    return `#${variantId} ${modeLabel(mode)}`
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 rounded-xl bg-muted/50 p-2.5">
        <Sparkles className="ml-1 size-4 text-stage-translate" aria-hidden />
        <AiProviderSelect
          providers={providers}
          value={providerId}
          onChange={onProviderChange}
          disabled={extracting}
        />
        <Button type="button" variant="outline" size="sm" disabled={extracting} onClick={() => void handleExtract()}>
          {extracting ? <Spinner /> : null}
          {extracting ? t("translate.namesExtracting") : t("translate.namesExtract")}
        </Button>
        {extracting ? <span className="text-[13px] text-muted-foreground">{t("translate.namesExtractSlow")}</span> : null}
      </div>

      <div className="sticky top-14 z-20 -mx-1 flex lg:top-0 flex-wrap items-center gap-2 bg-card/95 px-1 py-1.5 backdrop-blur supports-backdrop-filter:bg-card/80">
        <SegmentedTabs
          value={statusFilter}
          onChange={setStatusFilter}
          items={[
            { value: "all", label: t("translate.filterAll"), count: names.length },
            {
              value: "candidate",
              label: t("translate.nameStatus_candidate"),
              count: names.filter((n) => n.status === "candidate").length,
            },
            {
              value: "approved",
              label: t("translate.nameStatus_approved"),
              count: names.filter((n) => n.status === "approved").length,
            },
          ]}
        />
        <select
          aria-label={t("translate.nameKind")}
          className="h-9 rounded-lg border border-input bg-card px-2.5 text-sm"
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
        >
          <option value="__all__">{t("translate.nameKindAll")}</option>
          {NAME_KINDS.map((k) => (
            <option key={k || "none"} value={k}>
              {kindLabel(k)}
            </option>
          ))}
        </select>
        <div className="relative w-full sm:w-56">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            className="pl-8"
            placeholder={t("translate.namesSearch")}
            aria-label={t("translate.namesSearch")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={approving || candidatesVisible.length === 0}
          onClick={() => void approve(candidatesVisible.map((n) => n.id))}
        >
          {t("translate.namesApproveVisible", { count: candidatesVisible.length })}
        </Button>
      </div>

      {names.length === 0 ? (
        <EmptyState icon={Users} tone="translate" compact title={t("translate.namesEmpty")} />
      ) : filtered.length === 0 ? (
        <EmptyState icon={Search} tone="neutral" compact title={t("translate.segmentsFilterEmpty")} />
      ) : (
        <div className="max-h-[60vh] overflow-auto rounded-xl border border-border">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="sticky top-0 z-10 bg-muted text-xs font-semibold tracking-[0.06em] text-muted-foreground uppercase">
              <tr>
                <th className="px-3 py-2 text-left">{t("translate.termSrc")}</th>
                <th className="px-3 py-2 text-left">{t("translate.namesCurrent")}</th>
                <th className="px-3 py-2 text-left">{t("translate.namesNewTarget")}</th>
                <th className="px-3 py-2 text-left">{t("translate.nameKind")}</th>
                <th className="px-3 py-2 text-left">{t("translate.nameStatus")}</th>
                <th className="px-3 py-2 text-left">{t("translate.namesCounts")}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((n, i) => {
                const st = draftState(n)
                return (
                  <tr
                    key={n.id}
                    className={cn(
                      "transition-colors hover:bg-muted/50",
                      st === "dirty" && "bg-warning-soft hover:bg-warning-soft",
                      st === "empty" && "bg-danger-soft hover:bg-danger-soft",
                    )}
                  >
                    <td className="px-3 py-2 font-medium">
                      {n.source_term}
                      {n.notes ? <p className="text-xs font-normal text-muted-foreground">{n.notes}</p> : null}
                    </td>
                    <td className="px-3 py-2">{n.target_term || "—"}</td>
                    <td className="px-3 py-2">
                      <Input
                        ref={(el) => {
                          inputsRef.current[i] = el
                        }}
                        className="min-w-36"
                        aria-label={t("translate.namesNewTargetFor", { term: n.source_term })}
                        aria-invalid={st === "empty" || undefined}
                        value={drafts[n.id] ?? n.target_term}
                        onChange={(e) => {
                          const v = e.target.value
                          setDrafts((d) => ({ ...d, [n.id]: v }))
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
                        value={n.kind || ""}
                        onChange={(e) => void changeKind(n, e.target.value as NameKind)}
                      >
                        {NAME_KINDS.map((k) => (
                          <option key={k || "none"} value={k}>
                            {kindLabel(k)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <StatusPill
                        status={n.status}
                        tone={n.status === "approved" ? "success" : "warning"}
                        live={false}
                        label={t(`translate.nameStatus_${n.status}`)}
                      />
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      <p>{t("translate.namesSourceChapters", { count: n.source_chapter_count })}</p>
                      {n.output_hits.map((h) => (
                        <p key={h.variant_id}>
                          {variantLabel(h.variant_id, h.mode)}: {t("translate.renameSegmentsCount", { count: h.segments })}
                        </p>
                      ))}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {n.status === "candidate" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={approving}
                          onClick={() => void approve([n.id])}
                        >
                          {t("translate.namesApprove")}
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        aria-label={t("common.confirmDelete")}
                        onClick={() => void removeName(n)}
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
        <div className="ml-auto flex gap-2">
          {hasOutput ? (
            <Button type="button" size="sm" disabled={dirty.length === 0 || hasEmpty} onClick={openPreview}>
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
      {!hasOutput ? <p className="text-[13px] text-muted-foreground">{t("translate.namesNoOutputHint")}</p> : null}

      <RenamePreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        title={t("translate.renamePreviewTitle")}
        preview={preview}
        loading={previewLoading}
        applying={applying}
        variants={outputVariants.map((v) => ({ id: v.id, label: variantLabel(v.id, v.mode) }))}
        selectedVariantIds={variantIds}
        onSelectedVariantsChange={(ids) => {
          setVariantIds(ids)
          if (ids.length > 0) void runPreview(ids)
          else setPreview(null)
        }}
        onApply={() => void handleApply()}
      />
      {confirmDialog}
    </div>
  )
}
