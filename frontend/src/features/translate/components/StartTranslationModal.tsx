/** Modal "Bắt đầu dịch": chọn AI đã lưu + Dịch đầy đủ / Dịch tóm tắt (mục Nâng
 * cao mở ra pov/audio_cut/style_clone chi tiết qua ModeParamsFields). Submit ->
 * tạo Variant (nếu chưa có) rồi Start Job trong 1 luồng. */
import { useEffect, useState } from "react"
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
import { ApiError } from "@/api/client"
import { cn } from "@/lib/utils"
import { translateApi } from "../api"
import { getCatalogEntry } from "../providerProfiles"
import { ModeParamsFields, defaultModeParams } from "./ModeParamsFields"
import type { AiProvider, Estimate, StyleProfile, Work } from "../types"

type SummaryLength = "short" | "medium" | "long"

const SUMMARY_PRESETS: Record<SummaryLength, Record<string, unknown>> = {
  short: { target_minutes: 5, max_chars: 6000, keep_dialogue_ratio: 0.7 },
  medium: { target_minutes: 10, max_chars: 12000, keep_dialogue_ratio: 0.7 },
  long: { target_minutes: 20, max_chars: 24000, keep_dialogue_ratio: 0.7 },
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  work: Work
  existingVariantId?: number | null
  styleProfiles: StyleProfile[]
  /** variantId đã có job chạy — có thể là variant vừa chọn, hoặc variant `full`
   * nếu phải chờ fork (xem handleSubmit). */
  onStarted: (variantId: number, jobId: number) => void
}

export function StartTranslationModal({
  open,
  onOpenChange,
  work,
  existingVariantId,
  styleProfiles,
  onStarted,
}: Props) {
  const workId = work.id
  const t = useT()
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [aiIds, setAiIds] = useState<number[]>([])
  /** model theo AI id cho job này — mặc định lấy từ Settings khi mới tick. */
  const [modelByAi, setModelByAi] = useState<Record<number, string>>({})
  const [useAllKeysFor, setUseAllKeysFor] = useState<Record<number, boolean>>({})
  const [aiMode, setAiMode] = useState<"pool" | "fallback">("pool")
  const [primary, setPrimary] = useState<"full" | "summary">("full")
  const [summaryLength, setSummaryLength] = useState<SummaryLength>("medium")
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [advMode, setAdvMode] = useState("pov")
  const [advParams, setAdvParams] = useState<Record<string, unknown>>(defaultModeParams("pov"))
  const [busy, setBusy] = useState(false)
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [trackStoryState, setTrackStoryState] = useState(false)

  useEffect(() => {
    if (!open) return
    translateApi
      .listAiProviders()
      .then((list) => {
        setProviders(list)
        setAiIds((cur) => {
          const stillValid = cur.filter((id) => list.some((p) => p.id === id))
          if (stillValid.length > 0) {
            setModelByAi((m) => {
              const next = { ...m }
              for (const id of stillValid) {
                const p = list.find((x) => x.id === id)
                if (p && !next[id]) next[id] = p.model
              }
              return next
            })
            return stillValid
          }
          // Ưu tiên AI thật trước — tránh vô tình chọn nhầm Mock (kết quả giả).
          const preferred = list.find((p) => p.kind !== "mock")?.id ?? list[0]?.id
          if (preferred != null) {
            const p = list.find((x) => x.id === preferred)
            if (p) setModelByAi({ [preferred]: p.model })
            return [preferred]
          }
          return []
        })
      })
      .catch(() => setProviders([]))
  }, [open, workId])

  // Ước chi phí cập nhật theo mode đang chọn — audio_cut tốn hơn (2 pass: trích
  // beats rồi mới condense), không dùng chung 1 con số tĩnh cho mọi mode.
  useEffect(() => {
    if (!open) return
    const { mode } = resolveModeAndParams()
    translateApi
      .estimateWork(workId, mode)
      .then(setEstimate)
      .catch(() => setEstimate(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workId, primary, summaryLength, advancedOpen, advMode])

  function toggleAi(id: number) {
    setAiIds((cur) => {
      if (cur.includes(id)) {
        setModelByAi((m) => {
          const next = { ...m }
          delete next[id]
          return next
        })
        return cur.filter((x) => x !== id)
      }
      const p = providers.find((x) => x.id === id)
      if (p) setModelByAi((m) => ({ ...m, [id]: m[id] || p.model }))
      return [...cur, id]
    })
  }

  function modelFor(aiId: number): string {
    const sel = modelByAi[aiId]
    if (sel?.trim()) return sel.trim()
    return providers.find((x) => x.id === aiId)?.model ?? ""
  }

  function modelOptions(p: AiProvider): string[] {
    const cat = getCatalogEntry(p.kind)
    const suggestions = cat?.model_suggestions ?? []
    const cur = modelFor(p.id) || p.model
    const out = [...suggestions]
    if (cur && !out.includes(cur)) out.unshift(cur)
    if (p.model && !out.includes(p.model)) out.unshift(p.model)
    return out
  }

  /** Số key sẽ dùng cho 1 AI — >1 chỉ khi user bật "dùng tất cả key đã lưu"
   * (kiểu AiNiee/Glossarion: nhiều key CÙNG 1 model né rate-limit). */
  function keyCountFor(aiId: number): number {
    if (!useAllKeysFor[aiId]) return 1
    return providers.find((x) => x.id === aiId)?.key_count ?? 1
  }

  const totalSlots = aiIds.reduce((sum, id) => sum + keyCountFor(id), 0)

  function buildJobConfig() {
    const selections = aiIds.map((id) => ({
      ai_provider_id: id,
      model: modelFor(id) || undefined,
      use_all_keys: !!useAllKeysFor[id],
    }))
    if (totalSlots >= 2) {
      return { ai_selections: selections, ai_mode: aiMode }
    }
    // 1 slot: vẫn gửi ai_selections để model override không bị bỏ qua
    return { ai_selections: selections }
  }

  function resolveModeAndParams(): { mode: string; mode_params: Record<string, unknown> } {
    const extra = trackStoryState ? { track_story_state: true } : {}
    if (advancedOpen) return { mode: advMode, mode_params: { ...advParams, ...extra } }
    if (primary === "full") return { mode: "full", mode_params: extra }
    return { mode: "audio_cut", mode_params: { ...SUMMARY_PRESETS[summaryLength], ...extra } }
  }

  async function handleSubmit() {
    if (aiIds.length === 0) {
      toast.error(t("translate.pickAiForJob"))
      return
    }
    setBusy(true)
    try {
      const { mode, mode_params } = resolveModeAndParams()
      const cfg = buildJobConfig()

      if (mode === "full") {
        // Dùng lại existingVariantId chỉ khi nó ĐÚNG là variant full (mở modal
        // từ variant full có sẵn) — nếu lệch mode (vd modal mở sẵn cho 1 variant
        // khác) thì tạo variant full mới thay vì âm thầm bỏ qua lựa chọn của user.
        const existing = work.variants.find((v) => v.id === existingVariantId)
        const variantId =
          existing?.mode === "full" ? existing.id : (await translateApi.createVariant(workId, { mode, mode_params })).id
        const job = await translateApi.startJob(variantId, cfg)
        toast.success(t("translate.jobStarted"))
        onStarted(variantId, job.id)
        onOpenChange(false)
        return
      }

      // Mode khác full: BẮT BUỘC fork từ full (backend tự gắn source_variant_id).
      const v = await translateApi.createVariant(workId, { mode, mode_params })
      const freshWork = await translateApi.getWork(workId)
      const fullVariant = freshWork.variants.find((x) => x.id === v.source_variant_id)

      if (fullVariant?.status === "ready") {
        const job = await translateApi.startJob(v.id, cfg)
        toast.success(t("translate.jobStarted"))
        onStarted(v.id, job.id)
      } else if (fullVariant) {
        // full chưa dịch xong — start (hoặc dùng job đang chạy) của full trước;
        // variant vừa tạo tự chạy tiếp nhờ auto-chain phía backend khi full xong.
        let fullJobId = fullVariant.latest_job_id
        if (fullJobId == null) {
          const job = await translateApi.startJob(fullVariant.id, cfg)
          fullJobId = job.id
        }
        toast.message(t("translate.chainedOnFull"))
        onStarted(fullVariant.id, fullJobId)
      }
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  const selectedProviders = providers.filter((p) => aiIds.includes(p.id))
  const needsKeyWarning = selectedProviders.some((p) => p.requires_api_key && !p.has_api_key)
  const hasMockSelected = selectedProviders.some((p) => p.kind === "mock")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("translate.startModalTitle")}</DialogTitle>
          <DialogDescription>{t("translate.startModalHint")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t("translate.ai")}</label>
            <p className="text-xs text-muted-foreground">{t("translate.aiPickMultiHint")}</p>
            <p className="text-xs text-muted-foreground">{t("translate.jobModelHint")}</p>
            {providers.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {t("translate.noAiProvidersYet")}{" "}
                <a href="/translate/settings" className="underline underline-offset-2">
                  {t("translate.settings")}
                </a>
              </p>
            ) : (
              <div className="max-h-56 space-y-0.5 overflow-y-auto rounded-md border border-input p-1.5">
                {[...providers]
                  .sort((a, b) => Number(a.kind === "mock") - Number(b.kind === "mock"))
                  .map((p) => (
                    <div key={p.id} className="rounded px-1.5 py-1 hover:bg-muted/40">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={aiIds.includes(p.id)}
                          onChange={() => toggleAi(p.id)}
                        />
                        <span className="flex-1 truncate">
                          {p.label}
                          {p.kind === "mock" ? ` ${t("translate.mockSuffix")}` : ""}
                          {p.requires_api_key && !p.has_api_key ? ` — ${t("translate.noKey")}` : ""}
                        </span>
                      </label>
                      {aiIds.includes(p.id) ? (
                        <div className="ml-6 mt-1 space-y-1 pb-1">
                          <label className="flex flex-col gap-0.5 text-xs text-muted-foreground">
                            <span>{t("translate.jobModel")}</span>
                            <select
                              className="h-8 rounded-md border border-input bg-background px-2 font-mono text-xs text-foreground"
                              value={
                                modelOptions(p).includes(modelFor(p.id))
                                  ? modelFor(p.id)
                                  : "__custom__"
                              }
                              onChange={(e) => {
                                const v = e.target.value
                                if (v === "__custom__") {
                                  setModelByAi((m) => ({ ...m, [p.id]: "" }))
                                  return
                                }
                                setModelByAi((m) => ({ ...m, [p.id]: v }))
                              }}
                            >
                              {modelOptions(p).map((m) => (
                                <option key={m} value={m}>
                                  {m}
                                  {m === p.model ? ` (${t("translate.modelDefaultShort")})` : ""}
                                </option>
                              ))}
                              <option value="__custom__">{t("settings.customModel")}</option>
                            </select>
                          </label>
                          {!modelOptions(p).includes(modelFor(p.id)) || modelFor(p.id) === "" ? (
                            <input
                              className="h-8 w-full rounded-md border border-input bg-background px-2 font-mono text-xs"
                              value={modelFor(p.id)}
                              onChange={(e) =>
                                setModelByAi((m) => ({ ...m, [p.id]: e.target.value }))
                              }
                              placeholder="model-id"
                            />
                          ) : null}
                          {p.key_count > 1 ? (
                            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                              <input
                                type="checkbox"
                                checked={!!useAllKeysFor[p.id]}
                                onChange={() =>
                                  setUseAllKeysFor((cur) => ({ ...cur, [p.id]: !cur[p.id] }))
                                }
                              />
                              {t("translate.useAllKeysToggle", { count: String(p.key_count) })}
                            </label>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ))}
              </div>
            )}
            {totalSlots >= 2 ? (
              <div className="space-y-1.5 rounded-md border border-border bg-muted/30 px-2.5 py-2">
                <div className="flex gap-3">
                  <label className="flex items-center gap-1.5 text-xs">
                    <input
                      type="radio"
                      name="ai-mode"
                      checked={aiMode === "pool"}
                      onChange={() => setAiMode("pool")}
                    />
                    {t("translate.aiModePool")}
                  </label>
                  <label className="flex items-center gap-1.5 text-xs">
                    <input
                      type="radio"
                      name="ai-mode"
                      checked={aiMode === "fallback"}
                      onChange={() => setAiMode("fallback")}
                    />
                    {t("translate.aiModeFallback")}
                  </label>
                </div>
                <p className="text-xs text-muted-foreground">
                  {aiMode === "pool"
                    ? t("translate.poolHint", { count: String(totalSlots) })
                    : t("translate.fallbackHint", { count: String(totalSlots) })}
                </p>
              </div>
            ) : null}
            {needsKeyWarning ? (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                {t("translate.needKeyInSettings")}
              </p>
            ) : null}
            {hasMockSelected ? (
              <p className="text-xs text-amber-600 dark:text-amber-400">{t("translate.mockWarning")}</p>
            ) : null}
          </div>

          <label className="flex items-start gap-2 text-xs">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={trackStoryState}
              onChange={(e) => setTrackStoryState(e.target.checked)}
            />
            <span>
              {t("translate.trackStoryState")}
              <span className="block text-muted-foreground">{t("translate.trackStoryStateHint")}</span>
            </span>
          </label>

          {estimate ? (
            <div className="space-y-1 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              <p>
                {t("translate.estimateLine", {
                  chapters: String(estimate.chapter_count),
                  tokens: String(estimate.estimated_tokens),
                  usd: estimate.estimated_usd.toFixed(4),
                  budget: estimate.budget_usd > 0 ? `$${estimate.budget_usd}` : t("translate.noBudget"),
                })}
              </p>
              {estimate.over_budget ? (
                <p className="text-amber-600 dark:text-amber-400">{t("translate.overBudget")}</p>
              ) : null}
            </div>
          ) : null}

          {!advancedOpen ? (
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">
                {t("translate.pickVariantKind")}
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setPrimary("full")}
                  className={cn(
                    "rounded-lg border px-3 py-2.5 text-left text-sm transition-colors",
                    primary === "full"
                      ? "border-primary bg-primary/5 font-medium"
                      : "border-border hover:bg-muted/60",
                  )}
                >
                  {t("translate.fullModeTitle")}
                  <p className="mt-0.5 text-xs font-normal text-muted-foreground">
                    {t("translate.fullModeHint")}
                  </p>
                </button>
                <button
                  type="button"
                  onClick={() => setPrimary("summary")}
                  className={cn(
                    "rounded-lg border px-3 py-2.5 text-left text-sm transition-colors",
                    primary === "summary"
                      ? "border-primary bg-primary/5 font-medium"
                      : "border-border hover:bg-muted/60",
                  )}
                >
                  {t("translate.summaryModeTitle")}
                  <p className="mt-0.5 text-xs font-normal text-muted-foreground">
                    {t("translate.summaryModeHint")}
                  </p>
                </button>
              </div>

              {primary === "summary" ? (
                <div className="flex gap-2">
                  {(["short", "medium", "long"] as SummaryLength[]).map((len) => (
                    <button
                      key={len}
                      type="button"
                      onClick={() => setSummaryLength(len)}
                      className={cn(
                        "flex-1 rounded-md border px-2 py-1.5 text-xs transition-colors",
                        summaryLength === len
                          ? "border-primary bg-primary/5 font-medium"
                          : "border-border hover:bg-muted/60",
                      )}
                    >
                      {t(`translate.summaryLength${len[0].toUpperCase()}${len.slice(1)}`)}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <button
            type="button"
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            {advancedOpen ? t("translate.hideAdvanced") : t("translate.showAdvancedModes")}
          </button>

          {advancedOpen ? (
            <ModeParamsFields
              mode={advMode}
              onModeChange={setAdvMode}
              params={advParams}
              onParamsChange={(updater) => setAdvParams((p) => updater(p))}
              styleProfiles={styleProfiles}
            />
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button type="button" disabled={busy || aiIds.length === 0} onClick={() => void handleSubmit()}>
            {busy ? t("common.saving") : t("translate.startJob")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
