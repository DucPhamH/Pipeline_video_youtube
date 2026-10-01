/** Modal "Bắt đầu dịch" dạng từng bước: AI → Kiểu dịch → Tuỳ chọn → Ước tính & chạy.
 * Kiểu dịch chọn bằng thẻ (Đầy đủ / Tóm tắt / POV / Văn phong / Cắt cho audio /
 * Đổi vỏ); tuỳ chọn riêng từng mode qua ModeParamsFields. Submit -> tạo Variant
 * (nếu chưa có) rồi Start Job trong 1 luồng. */
import { useEffect, useRef, useState, type ComponentType, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { AlertTriangle, Check, ChevronLeft, ChevronRight, ListCollapse } from "lucide-react"
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
import { modeVisual, useModeBlurb, useModeTitle, useParamsSummary } from "./variantVisual"
import { cleanModeParams, modeParamsError } from "../reskinParams"
import { Spinner } from "./RenameShared"
import { useConfirm } from "@/components/useConfirm"
import type { AiProvider, Estimate, StyleProfile, Variant, Work } from "../types"

type SummaryLength = "short" | "medium" | "long"

const SUMMARY_PRESETS: Record<SummaryLength, Record<string, unknown>> = {
  short: { target_minutes: 5, max_chars: 6000, keep_dialogue_ratio: 0.7 },
  medium: { target_minutes: 10, max_chars: 12000, keep_dialogue_ratio: 0.7 },
  long: { target_minutes: 20, max_chars: 24000, keep_dialogue_ratio: 0.7 },
}

/** Lựa chọn trên thẻ: "summary" = audio_cut theo preset độ dài; còn lại = mode thật. */
type Choice = "full" | "summary" | "pov" | "style_clone" | "audio_cut" | "reskin"
const CHOICES: Choice[] = ["full", "summary", "pov", "style_clone", "audio_cut", "reskin"]
const ADVANCED: Choice[] = ["pov", "style_clone", "audio_cut", "reskin"]

type Step = 0 | 1 | 2 | 3

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  work: Work
  existingVariantId?: number | null
  styleProfiles: StyleProfile[]
  /** Mở sẵn với kiểu dịch này (vd từ ô "Tạo nhanh" trên Book hub). */
  initialMode?: string | null
  /** variantId đã có job chạy — có thể là variant vừa chọn, hoặc variant `full`
   * nếu phải chờ fork (xem handleSubmit). */
  onStarted: (variantId: number, jobId: number) => void
  /** "Duyệt tên trước khi dịch": đã trích tên xong → mở tab Tên thay vì chạy job. */
  onReviewNames?: () => void
  /** Variant reskin vừa tạo → mở bảng đổi vỏ trước khi chạy job. */
  onReviewSkinMap?: (variantId: number) => void
}

/** JSON với key đã sắp xếp — so params không phụ thuộc thứ tự key. */
function stableKey(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stableKey).join(",")}]`
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>
    return `{${Object.keys(o)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${stableKey(o[k])}`)
      .join(",")}}`
  }
  return JSON.stringify(v)
}

function OptionToggle({
  checked,
  onChange,
  title,
  hint,
  highlight,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  title: string
  hint: string
  highlight?: boolean
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-xl border px-3.5 py-3 transition-colors",
        checked ? "border-primary/50 bg-accent/60" : "border-border hover:bg-muted/60",
        highlight && !checked && "border-primary/30",
      )}
    >
      <input
        type="checkbox"
        className="mt-1 size-4 shrink-0 accent-primary"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-[13px] text-muted-foreground">{hint}</span>
      </span>
    </label>
  )
}

export function StartTranslationModal({
  open,
  onOpenChange,
  work,
  existingVariantId,
  styleProfiles,
  initialMode,
  onStarted,
  onReviewNames,
  onReviewSkinMap,
}: Props) {
  const workId = work.id
  const t = useT()
  const modeTitle = useModeTitle()
  const modeBlurb = useModeBlurb()
  const paramsSummary = useParamsSummary(styleProfiles)
  const [confirm, confirmDialog] = useConfirm()
  const [step, setStep] = useState<Step>(0)
  const [reviewNames, setReviewNames] = useState(false)
  const [reviewSkinMap, setReviewSkinMap] = useState(true)
  const [phase, setPhase] = useState<"" | "extracting">("")
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [aiIds, setAiIds] = useState<number[]>([])
  /** model theo AI id cho job này — mặc định lấy từ Settings khi mới tick. */
  const [modelByAi, setModelByAi] = useState<Record<number, string>>({})
  const [useAllKeysFor, setUseAllKeysFor] = useState<Record<number, boolean>>({})
  const [aiMode, setAiMode] = useState<"pool" | "fallback">("pool")
  const [choice, setChoice] = useState<Choice>("full")
  const [summaryLength, setSummaryLength] = useState<SummaryLength>("medium")
  const [advParams, setAdvParams] = useState<Record<string, unknown>>(defaultModeParams("pov"))
  const [busy, setBusy] = useState(false)
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [trackStoryState, setTrackStoryState] = useState(false)
  const [polish, setPolish] = useState(false)
  /** Variant đã tạo trong phiên mở modal này (theo mode+params) — bấm Start lại
   * sau lỗi dùng lại nó thay vì tạo thêm variant mồ côi/trùng. */
  const createdVariantRef = useRef<{ key: string; variant: Variant } | null>(null)

  const advanced = ADVANCED.includes(choice)

  // Variant có sẵn không phải full (vd reskin vừa tạo, chưa có job) → chọn sẵn
  // đúng mode/params của nó để Start chạy chính variant đó.
  const existingVariant = work.variants.find((v) => v.id === existingVariantId) ?? null
  const existingNonFull =
    existingVariant && existingVariant.mode !== "full" && existingVariant.latest_job_id == null
      ? existingVariant
      : null

  useEffect(() => {
    if (!open) return
    createdVariantRef.current = null
    setReviewNames(false)
    setReviewSkinMap(true)
    setStep(0)
    if (existingNonFull) {
      const { track_story_state, polish: pol, ...rest } = existingNonFull.mode_params ?? {}
      setChoice((CHOICES.includes(existingNonFull.mode as Choice) ? existingNonFull.mode : "pov") as Choice)
      setAdvParams(rest)
      setTrackStoryState(Boolean(track_story_state))
      setPolish(Boolean(pol))
    } else if (initialMode && CHOICES.includes(initialMode as Choice)) {
      const c = initialMode as Choice
      setChoice(c)
      if (ADVANCED.includes(c)) setAdvParams(defaultModeParams(c))
    }
    // chỉ khi mở modal
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

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
    // API estimate chỉ nhận mode + polish (không nhận mode_params).
    const { mode } = resolveModeAndParams()
    let stale = false
    translateApi
      .estimateWork(workId, mode, polish)
      .then((e) => {
        if (!stale) setEstimate(e)
      })
      .catch(() => {
        if (!stale) setEstimate(null)
      })
    return () => {
      stale = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workId, choice, summaryLength, polish])

  function pickChoice(c: Choice) {
    if (c === choice) return
    setChoice(c)
    if (ADVANCED.includes(c)) setAdvParams(defaultModeParams(c))
  }

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
    const extra: Record<string, unknown> = {}
    if (trackStoryState) extra.track_story_state = true
    if (polish) extra.polish = true
    if (advanced) return { mode: choice, mode_params: { ...cleanModeParams(choice, advParams), ...extra } }
    if (choice === "full") return { mode: "full", mode_params: extra }
    return { mode: "audio_cut", mode_params: { ...SUMMARY_PRESETS[summaryLength], ...extra } }
  }

  async function getOrCreateVariant(mode: string, mode_params: Record<string, unknown>): Promise<Variant> {
    const key = stableKey([mode, mode_params])
    const cached = createdVariantRef.current
    if (cached && cached.key === key) return cached.variant
    if (existingNonFull && stableKey([existingNonFull.mode, cleanModeParams(existingNonFull.mode, existingNonFull.mode_params ?? {})]) === key) {
      createdVariantRef.current = { key, variant: existingNonFull }
      return existingNonFull
    }
    const v = await translateApi.createVariant(workId, { mode, mode_params })
    createdVariantRef.current = { key, variant: v }
    return v
  }

  const paramsErr = advanced ? modeParamsError(choice, advParams, t) : null

  async function handleSubmit() {
    if (aiIds.length === 0) {
      toast.error(t("translate.pickAiForJob"))
      setStep(0)
      return
    }
    if (paramsErr) {
      toast.error(paramsErr)
      setStep(2)
      return
    }
    setBusy(true)
    try {
      const { mode, mode_params } = resolveModeAndParams()
      const cfg = buildJobConfig()

      const wantsSkinReview = mode === "reskin" && reviewSkinMap && !existingNonFull && !!onReviewSkinMap
      if (reviewNames || wantsSkinReview) {
        if (reviewNames) {
          const names = await translateApi.listNames(workId).catch(() => [])
          let extract = names.length === 0
          if (!extract) {
            extract = await confirm({
              title: t("translate.namesExtractTitle"),
              description: t("translate.namesExtractAgainConfirm", { count: names.length }),
              confirmLabel: t("translate.namesExtract"),
              destructive: false,
            })
          }
          if (extract) {
            setPhase("extracting")
            const r = await translateApi.extractNames(workId, { provider_id: aiIds[0] })
            toast.success(t("translate.namesExtracted", { count: r.added }))
          }
        }
        if (wantsSkinReview) {
          const v = await getOrCreateVariant(mode, mode_params)
          onReviewSkinMap?.(v.id)
        } else {
          onReviewNames?.()
        }
        onOpenChange(false)
        return
      }

      if (mode === "full") {
        // Dùng lại existingVariantId chỉ khi nó ĐÚNG là variant full (mở modal
        // từ variant full có sẵn) — nếu lệch mode (vd modal mở sẵn cho 1 variant
        // khác) thì tạo variant full mới thay vì âm thầm bỏ qua lựa chọn của user.
        const existing = work.variants.find((v) => v.id === existingVariantId)
        const variantId =
          existing?.mode === "full" ? existing.id : (await getOrCreateVariant(mode, mode_params)).id
        const job = await translateApi.startJob(variantId, cfg)
        toast.success(t("translate.jobStarted"))
        onStarted(variantId, job.id)
        onOpenChange(false)
        return
      }

      // Mode khác full: BẮT BUỘC fork từ full (backend tự gắn source_variant_id).
      const v = await getOrCreateVariant(mode, mode_params)
      const freshWork = await translateApi.getWork(workId)
      const fullVariant = freshWork.variants.find((x) => x.id === v.source_variant_id)

      if (!fullVariant) {
        // Backend không gắn được variant full nguồn — báo lỗi, giữ modal mở.
        toast.error(t("translate.chainSourceMissing"))
        return
      }
      if (fullVariant.status === "ready") {
        const job = await translateApi.startJob(v.id, cfg)
        toast.success(t("translate.jobStarted"))
        onStarted(v.id, job.id)
      } else {
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
      setPhase("")
    }
  }

  const reskinPicked = choice === "reskin"
  const reviewing = reviewNames || (reskinPicked && reviewSkinMap && !existingNonFull && !!onReviewSkinMap)

  const selectedProviders = providers.filter((p) => aiIds.includes(p.id))
  const needsKeyWarning = selectedProviders.some((p) => p.requires_api_key && !p.has_api_key)
  const hasMockSelected = selectedProviders.some((p) => p.kind === "mock")

  const steps: { label: string; done: boolean }[] = [
    { label: t("translate.hub.stepAi"), done: aiIds.length > 0 },
    { label: t("translate.hub.stepMode"), done: true },
    { label: t("translate.hub.stepOptions"), done: !paramsErr },
    { label: t("translate.hub.stepStart"), done: false },
  ]

  function goNext() {
    if (step === 0 && aiIds.length === 0) {
      toast.error(t("translate.pickAiForJob"))
      return
    }
    if (step === 2 && paramsErr) {
      toast.error(paramsErr)
      return
    }
    setStep((s) => Math.min(3, s + 1) as Step)
  }

  const choiceMode = choice === "summary" ? "audio_cut" : choice
  const choiceTitle = (c: Choice) => (c === "summary" ? t("translate.summaryModeTitle") : modeTitle(c))
  const choiceBlurb = (c: Choice) => (c === "summary" ? t("translate.summaryModeHint") : modeBlurb(c))
  const { mode_params: resolvedParams } = resolveModeAndParams()

  return (
    <Dialog open={open} onOpenChange={(o) => (busy && !o ? undefined : onOpenChange(o))}>
      <DialogContent className="gap-5 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("translate.startModalTitle")}</DialogTitle>
          <DialogDescription>{t("translate.startModalHint")}</DialogDescription>
        </DialogHeader>

        <ol className="grid grid-cols-4 gap-2" aria-label={t("translate.startModalTitle")}>
          {steps.map((s, i) => {
            const current = i === step
            const passed = i < step
            return (
              <li key={i} className="min-w-0">
                <button
                  type="button"
                  onClick={() => setStep(i as Step)}
                  aria-current={current ? "step" : undefined}
                  className="group flex w-full flex-col gap-1.5 rounded-md text-left focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  <span
                    className={cn(
                      "h-1 rounded-full transition-colors",
                      current || passed ? "bg-primary" : "bg-track",
                    )}
                  />
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span
                      className={cn(
                        "flex size-5 shrink-0 items-center justify-center rounded-full font-mono text-xs font-semibold",
                        passed && s.done
                          ? "bg-primary text-primary-foreground"
                          : current
                            ? "bg-accent text-accent-foreground ring-1 ring-primary"
                            : "bg-muted text-muted-foreground",
                      )}
                    >
                      {passed && s.done ? <Check className="size-3" aria-hidden /> : i + 1}
                    </span>
                    <span
                      className={cn(
                        "truncate text-[13px] font-medium",
                        current ? "text-foreground" : "text-muted-foreground group-hover:text-foreground",
                      )}
                    >
                      {s.label}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ol>

        <div className="min-h-[16rem] space-y-4">
          {step === 0 ? (
            <section className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {t("translate.aiPickMultiHint")} {t("translate.jobModelHint")}
              </p>
              {providers.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
                  {t("translate.noAiProvidersYet")}{" "}
                  <Link
                    to="/translate/settings"
                    className="font-medium text-accent-foreground underline underline-offset-2"
                    onClick={() => onOpenChange(false)}
                  >
                    {t("translate.settings")}
                  </Link>
                </div>
              ) : (
                <ul className="stagger max-h-[46vh] space-y-2 overflow-y-auto pr-0.5">
                  {[...providers]
                    .sort((a, b) => Number(a.kind === "mock") - Number(b.kind === "mock"))
                    .map((p) => {
                      const on = aiIds.includes(p.id)
                      return (
                        <li
                          key={p.id}
                          className={cn(
                            "rounded-xl border transition-colors",
                            on ? "border-primary/50 bg-accent/50" : "border-border hover:bg-muted/50",
                          )}
                        >
                          <label className="flex cursor-pointer items-center gap-3 px-3.5 py-2.5">
                            <input
                              type="checkbox"
                              className="size-4 accent-primary"
                              checked={on}
                              onChange={() => toggleAi(p.id)}
                            />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium">
                                {p.label}
                                {p.kind === "mock" ? ` ${t("translate.mockSuffix")}` : ""}
                              </span>
                              <span className="block truncate font-mono text-xs text-muted-foreground">
                                {p.kind} · {p.model || "—"}
                              </span>
                            </span>
                            {p.requires_api_key && !p.has_api_key ? (
                              <span className="shrink-0 rounded-full bg-warning-soft px-2 py-0.5 text-xs font-semibold text-warning">
                                {t("translate.noKey")}
                              </span>
                            ) : null}
                          </label>
                          {on ? (
                            <div className="grid gap-2 border-t border-primary/15 px-3.5 py-2.5 sm:grid-cols-2">
                              <label className="flex flex-col gap-1 text-[13px] text-muted-foreground">
                                <span>{t("translate.jobModel")}</span>
                                <select
                                  className="h-9 rounded-lg border border-input bg-card px-2.5 font-mono text-[13px] text-foreground"
                                  value={modelOptions(p).includes(modelFor(p.id)) ? modelFor(p.id) : "__custom__"}
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
                                <label className="flex flex-col gap-1 text-[13px] text-muted-foreground">
                                  <span>{t("settings.customModel")}</span>
                                  <input
                                    className="h-9 w-full rounded-lg border border-input bg-card px-2.5 font-mono text-[13px] text-foreground"
                                    value={modelFor(p.id)}
                                    onChange={(e) => setModelByAi((m) => ({ ...m, [p.id]: e.target.value }))}
                                    placeholder="model-id"
                                  />
                                </label>
                              ) : null}
                              {p.key_count > 1 ? (
                                <label className="flex items-center gap-2 text-[13px] sm:col-span-2">
                                  <input
                                    type="checkbox"
                                    className="size-4 accent-primary"
                                    checked={!!useAllKeysFor[p.id]}
                                    onChange={() => setUseAllKeysFor((cur) => ({ ...cur, [p.id]: !cur[p.id] }))}
                                  />
                                  {t("translate.useAllKeysToggle", { count: String(p.key_count) })}
                                </label>
                              ) : null}
                            </div>
                          ) : null}
                        </li>
                      )
                    })}
                </ul>
              )}
              {totalSlots >= 2 ? (
                <div className="space-y-2 rounded-xl border border-border bg-muted/40 p-3">
                  <div className="inline-flex gap-1 rounded-lg bg-card p-1 ring-1 ring-border" role="radiogroup">
                    {(["pool", "fallback"] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        role="radio"
                        aria-checked={aiMode === m}
                        onClick={() => setAiMode(m)}
                        className={cn(
                          "rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
                          aiMode === m ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {m === "pool" ? t("translate.aiModePool") : t("translate.aiModeFallback")}
                      </button>
                    ))}
                  </div>
                  <p className="text-[13px] text-muted-foreground">
                    {aiMode === "pool"
                      ? t("translate.poolHint", { count: String(totalSlots) })
                      : t("translate.fallbackHint", { count: String(totalSlots) })}
                  </p>
                </div>
              ) : null}
              {needsKeyWarning ? <Warn>{t("translate.needKeyInSettings")}</Warn> : null}
              {hasMockSelected ? <Warn>{t("translate.mockWarning")}</Warn> : null}
            </section>
          ) : null}

          {step === 1 ? (
            <section className="space-y-3">
              <p className="text-sm text-muted-foreground">{t("translate.pickVariantKind")}</p>
              <div className="stagger grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t("translate.pickVariantKind")}>
                {CHOICES.map((c) => {
                  const vis = modeVisual(c === "summary" ? "audio_cut" : c)
                  const Icon: ComponentType<{ className?: string }> = c === "summary" ? ListCollapse : vis.icon
                  const on = choice === c
                  const locked = existingNonFull != null && c !== existingNonFull.mode
                  return (
                    <button
                      key={c}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      disabled={locked}
                      onClick={() => pickChoice(c)}
                      className={cn(
                        "flex items-start gap-3 rounded-xl border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-45",
                        on ? "border-primary bg-accent/60 ring-1 ring-primary" : "border-border hover:bg-muted/60",
                      )}
                    >
                      <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-[10px]", vis.tint)}>
                        <Icon className="size-[18px]" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold">{choiceTitle(c)}</span>
                        <span className="block text-[13px] text-muted-foreground">{choiceBlurb(c)}</span>
                      </span>
                      {on ? <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden /> : null}
                    </button>
                  )
                })}
              </div>
            </section>
          ) : null}

          {step === 2 ? (
            <section className="space-y-4">
              {choice === "summary" ? (
                <div className="space-y-1.5">
                  <p className="text-sm font-medium">{t("translate.summaryModeTitle")}</p>
                  <div className="flex gap-2">
                    {(["short", "medium", "long"] as SummaryLength[]).map((len) => (
                      <button
                        key={len}
                        type="button"
                        aria-pressed={summaryLength === len}
                        onClick={() => setSummaryLength(len)}
                        className={cn(
                          "flex-1 rounded-lg border px-2 py-2 text-[13px] font-medium transition-colors",
                          summaryLength === len
                            ? "border-primary bg-accent text-accent-foreground"
                            : "border-border hover:bg-muted",
                        )}
                      >
                        {t(`translate.summaryLength${len[0].toUpperCase()}${len.slice(1)}`)}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {advanced ? (
                <div className="rounded-xl border border-border p-3.5">
                  <ModeParamsFields
                    key={choice}
                    mode={choice}
                    onModeChange={(m) => pickChoice(m as Choice)}
                    params={advParams}
                    onParamsChange={(updater) => setAdvParams((p) => updater(p))}
                    styleProfiles={styleProfiles}
                    hideModePicker
                  />
                </div>
              ) : null}

              <div className="grid gap-2">
                <OptionToggle
                  checked={trackStoryState}
                  onChange={setTrackStoryState}
                  title={t("translate.trackStoryState")}
                  hint={t("translate.trackStoryStateHint")}
                />
                <OptionToggle
                  checked={polish}
                  onChange={setPolish}
                  title={t("translate.polishPass")}
                  hint={t("translate.polishPassHint")}
                />
                {onReviewNames ? (
                  <OptionToggle
                    checked={reviewNames}
                    onChange={setReviewNames}
                    title={t("translate.reviewNamesFirst")}
                    hint={t("translate.reviewNamesFirstHint")}
                  />
                ) : null}
                {reskinPicked && !existingNonFull && onReviewSkinMap ? (
                  <OptionToggle
                    highlight
                    checked={reviewSkinMap}
                    onChange={setReviewSkinMap}
                    title={t("translate.reviewSkinMapFirst")}
                    hint={t("translate.reviewSkinMapFirstHint")}
                  />
                ) : null}
              </div>
            </section>
          ) : null}

          {step === 3 ? (
            <section className="space-y-3">
              <dl className="divide-y divide-border rounded-xl border border-border text-sm">
                <SummaryRow label={t("translate.hub.stepAi")} onEdit={() => setStep(0)} editLabel={t("common.edit")}>
                  {selectedProviders.length
                    ? selectedProviders.map((p) => `${p.label} (${modelFor(p.id) || "—"})`).join(", ")
                    : "—"}
                  {totalSlots >= 2
                    ? ` · ${aiMode === "pool" ? t("translate.aiModePool") : t("translate.aiModeFallback")}`
                    : ""}
                </SummaryRow>
                <SummaryRow label={t("translate.hub.stepMode")} onEdit={() => setStep(1)} editLabel={t("common.edit")}>
                  {choiceTitle(choice)}
                  {choice === "summary"
                    ? ` · ${t(`translate.summaryLength${summaryLength[0].toUpperCase()}${summaryLength.slice(1)}`)}`
                    : ""}
                  {advanced || polish ? (
                    <span className="block text-[13px] text-muted-foreground">
                      {paramsSummary(choiceMode, resolvedParams)}
                    </span>
                  ) : null}
                </SummaryRow>
                {trackStoryState || reviewNames || (reskinPicked && reviewSkinMap && onReviewSkinMap && !existingNonFull) ? (
                  <SummaryRow label={t("translate.hub.stepOptions")} onEdit={() => setStep(2)} editLabel={t("common.edit")}>
                    {[
                      trackStoryState ? t("translate.trackStoryState") : null,
                      reviewNames ? t("translate.reviewNamesFirst") : null,
                      reskinPicked && reviewSkinMap && onReviewSkinMap && !existingNonFull
                        ? t("translate.reviewSkinMapFirst")
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </SummaryRow>
                ) : null}
              </dl>

              {estimate ? (
                <div
                  className={cn(
                    "rounded-xl px-4 py-3",
                    estimate.over_budget ? "bg-warning-soft" : "bg-muted/60",
                  )}
                >
                  <div className="grid grid-cols-3 gap-3">
                    <Metric label={t("translate.chapters")} value={String(estimate.chapter_count)} />
                    <Metric label={t("translate.hub.tokens")} value={estimate.estimated_tokens.toLocaleString()} />
                    <Metric label={t("translate.hub.cost")} value={`$${estimate.estimated_usd.toFixed(4)}`} />
                  </div>
                  <p className="mt-2 text-[13px] text-muted-foreground">
                    {t("translate.estimateLine", {
                      chapters: String(estimate.chapter_count),
                      tokens: String(estimate.estimated_tokens),
                      usd: estimate.estimated_usd.toFixed(4),
                      budget: estimate.budget_usd > 0 ? `$${estimate.budget_usd}` : t("translate.noBudget"),
                    })}
                  </p>
                  {estimate.over_budget ? (
                    <p className="mt-1 flex items-center gap-1.5 text-[13px] font-medium text-warning">
                      <AlertTriangle className="size-4" aria-hidden />
                      {t("translate.overBudget")}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {needsKeyWarning ? <Warn>{t("translate.needKeyInSettings")}</Warn> : null}
              {hasMockSelected ? <Warn>{t("translate.mockWarning")}</Warn> : null}
            </section>
          ) : null}
        </div>

        <DialogFooter className="sm:items-center">
          <Button type="button" variant="ghost" className="sm:mr-auto" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          {step > 0 ? (
            <Button type="button" variant="outline" onClick={() => setStep((s) => Math.max(0, s - 1) as Step)}>
              <ChevronLeft aria-hidden />
              {t("translate.hub.back")}
            </Button>
          ) : null}
          {step < 3 ? (
            <Button type="button" onClick={goNext} disabled={step === 0 && aiIds.length === 0}>
              {t("translate.hub.next")}
              <ChevronRight aria-hidden />
            </Button>
          ) : (
            <Button type="button" disabled={busy || aiIds.length === 0} onClick={() => void handleSubmit()}>
              {phase === "extracting" ? <Spinner /> : null}
              {phase === "extracting"
                ? t("translate.namesExtracting")
                : busy
                  ? t("common.saving")
                  : reviewing
                    ? t("translate.continueToReview")
                    : t("translate.startJob")}
            </Button>
          )}
        </DialogFooter>
        {confirmDialog}
      </DialogContent>
    </Dialog>
  )
}

function Warn({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  )
}

function SummaryRow({
  label,
  children,
  onEdit,
  editLabel,
}: {
  label: string
  children: ReactNode
  onEdit: () => void
  editLabel: string
}) {
  return (
    <div className="flex items-start gap-3 px-3.5 py-2.5">
      <dt className="w-24 shrink-0 text-[13px] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1 break-words">{children}</dd>
      <button
        type="button"
        onClick={onEdit}
        className="shrink-0 text-[13px] font-medium text-accent-foreground hover:underline"
      >
        {editLabel}
      </button>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold tracking-[0.06em] text-muted-foreground uppercase">{label}</p>
      <p className="truncate font-mono text-[17px] font-medium tabular-nums">{value}</p>
    </div>
  )
}
