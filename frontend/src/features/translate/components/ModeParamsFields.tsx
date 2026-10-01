/** Chọn Variant mode + form params riêng từng mode — dùng chung cho modal
 * "Bắt đầu dịch" (mục Nâng cao) và tab Variant trên Work page. */
import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import type { StyleProfile } from "../types"
import { RESKIN_CUSTOM_MAX, RESKIN_INTENSITIES, RESKIN_NOTES_MAX, RESKIN_SETTINGS, parseNameList } from "../reskinParams"

export const MODES = ["full", "pov", "audio_cut", "style_clone", "reskin"] as const

export function defaultModeParams(mode: string): Record<string, unknown> {
  if (mode === "pov") return { target_pov: "first_person" }
  if (mode === "audio_cut") return { target_minutes: 10, max_chars: 12000, keep_dialogue_ratio: 0.7 }
  if (mode === "style_clone") return { style_profile_id: "web_novel_vn_shorts" }
  if (mode === "reskin") return { setting: "modern_urban", intensity: "medium" }
  return {}
}

export function useModeLabel() {
  const t = useT()
  return (mode: string) => {
    if (mode === "pov") return t("translate.modePov")
    if (mode === "audio_cut") return t("translate.modeAudioCut")
    if (mode === "style_clone") return t("translate.modeStyleClone")
    if (mode === "reskin") return t("translate.modeReskin")
    return t("translate.modeFull")
  }
}

type Props = {
  mode: string
  onModeChange: (mode: string) => void
  params: Record<string, unknown>
  onParamsChange: (updater: (p: Record<string, unknown>) => Record<string, unknown>) => void
  styleProfiles: StyleProfile[]
  modes?: readonly string[]
  /** Ẩn ô chọn mode (khi mode đã chọn bằng thẻ ở nơi khác, vd modal). */
  hideModePicker?: boolean
}

export function ModeParamsFields({
  mode,
  onModeChange,
  params,
  onParamsChange,
  styleProfiles,
  modes = MODES,
  hideModePicker = false,
}: Props) {
  const t = useT()
  const modeLabel = useModeLabel()

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {hideModePicker ? null : <div className="space-y-1">
        <Label htmlFor="mp-mode">{t("translate.variantMode")}</Label>
        <select
          id="mp-mode"
          className="flex h-9 w-full rounded-lg border border-input bg-card px-2.5 text-sm"
          value={mode}
          onChange={(e) => {
            const m = e.target.value
            onModeChange(m)
            onParamsChange(() => defaultModeParams(m))
          }}
        >
          {modes.map((m) => (
            <option key={m} value={m}>
              {modeLabel(m)}
            </option>
          ))}
        </select>
      </div>}

      {mode === "pov" ? (
        <>
          <div className="space-y-1">
            <Label htmlFor="mp-pov">{t("translate.targetPov")}</Label>
            <select
              id="mp-pov"
              className="flex h-9 w-full rounded-lg border border-input bg-card px-2.5 text-sm"
              value={String(params.target_pov || "first_person")}
              onChange={(e) => onParamsChange((p) => ({ ...p, target_pov: e.target.value }))}
            >
              <option value="first_person">{t("translate.povFirst")}</option>
              <option value="third_person">{t("translate.povThird")}</option>
              <option value="second_person">{t("translate.povSecond")}</option>
            </select>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="mp-vp">{t("translate.viewpointChar")}</Label>
            <Input
              id="mp-vp"
              value={String(params.viewpoint_character || "")}
              onChange={(e) => onParamsChange((p) => ({ ...p, viewpoint_character: e.target.value }))}
            />
          </div>
        </>
      ) : null}

      {mode === "audio_cut" ? (
        <>
          <div className="space-y-1">
            <Label htmlFor="mp-mins">{t("translate.targetMinutes")}</Label>
            <Input
              id="mp-mins"
              type="number"
              min={1}
              max={60}
              value={Number(params.target_minutes) || 10}
              onChange={(e) => onParamsChange((p) => ({ ...p, target_minutes: Number(e.target.value) }))}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mp-maxc">{t("translate.maxChars")}</Label>
            <Input
              id="mp-maxc"
              type="number"
              min={500}
              value={Number(params.max_chars) || 12000}
              onChange={(e) => onParamsChange((p) => ({ ...p, max_chars: Number(e.target.value) }))}
            />
          </div>
        </>
      ) : null}

      {mode === "style_clone" ? (
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="mp-style">{t("translate.styleProfile")}</Label>
          <select
            id="mp-style"
            className="flex h-9 w-full rounded-lg border border-input bg-card px-2.5 text-sm"
            value={String(params.style_profile_id || "web_novel_vn_shorts")}
            onChange={(e) => onParamsChange((p) => ({ ...p, style_profile_id: e.target.value }))}
          >
            {(styleProfiles.length
              ? styleProfiles
              : [{ id: "web_novel_vn_shorts", label: "Web novel VN ngắn", instruction: "" }]
            ).map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {mode === "reskin" ? <ReskinFields params={params} onParamsChange={onParamsChange} /> : null}
    </div>
  )
}

function ReskinFields({
  params,
  onParamsChange,
}: {
  params: Record<string, unknown>
  onParamsChange: Props["onParamsChange"]
}) {
  const t = useT()
  const setting = String(params.setting || "modern_urban")
  const intensity = String(params.intensity || "medium")
  const custom = String(params.custom_setting ?? "")
  const notes = String(params.notes ?? "")
  // Giữ chuỗi gõ tay riêng — parse mỗi phím sẽ nuốt dấu phẩy cuối.
  const [keepRaw, setKeepRaw] = useState(() =>
    Array.isArray(params.keep_names) ? (params.keep_names as string[]).join(", ") : "",
  )
  const customMissing = setting === "custom" && !custom.trim()

  return (
    <>
      <p className="text-xs text-muted-foreground sm:col-span-2">{t("translate.reskinHint")}</p>
      <div className="space-y-1 sm:col-span-2">
        <Label htmlFor="mp-rs-setting">{t("translate.reskinSetting")}</Label>
        <select
          id="mp-rs-setting"
          className="flex h-9 w-full rounded-lg border border-input bg-card px-2.5 text-sm"
          value={setting}
          onChange={(e) => onParamsChange((p) => ({ ...p, setting: e.target.value }))}
        >
          {RESKIN_SETTINGS.map((s) => (
            <option key={s} value={s}>
              {t(`translate.reskinSetting_${s}`)}
            </option>
          ))}
        </select>
      </div>
      {setting === "custom" ? (
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="mp-rs-custom">{t("translate.reskinCustomSetting")}</Label>
          <Textarea
            id="mp-rs-custom"
            rows={3}
            maxLength={RESKIN_CUSTOM_MAX}
            aria-invalid={customMissing || undefined}
            placeholder={t("translate.reskinCustomPlaceholder")}
            value={custom}
            onChange={(e) => onParamsChange((p) => ({ ...p, custom_setting: e.target.value }))}
          />
          <p className={cn("text-xs", customMissing ? "text-destructive" : "text-muted-foreground")}>
            {customMissing ? t("translate.reskinCustomRequired") : `${custom.length}/${RESKIN_CUSTOM_MAX}`}
          </p>
        </div>
      ) : null}
      <div className="space-y-1 sm:col-span-2">
        <Label>{t("translate.reskinIntensity")}</Label>
        <div className="flex gap-2" role="group" aria-label={t("translate.reskinIntensity")}>
          {RESKIN_INTENSITIES.map((lv) => (
            <button
              key={lv}
              type="button"
              aria-pressed={intensity === lv}
              onClick={() => onParamsChange((p) => ({ ...p, intensity: lv }))}
              className={cn(
                "flex-1 rounded-lg border px-2 py-2 text-[13px] font-medium transition-colors",
                intensity === lv ? "border-primary bg-accent text-accent-foreground" : "border-border hover:bg-muted",
              )}
            >
              {t(`translate.reskinIntensity_${lv}`)}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{t(`translate.reskinIntensityHint_${intensity}`)}</p>
      </div>
      <div className="space-y-1 sm:col-span-2">
        <Label htmlFor="mp-rs-keep">{t("translate.reskinKeepNames")}</Label>
        <Textarea
          id="mp-rs-keep"
          rows={2}
          placeholder={t("translate.reskinKeepNamesPlaceholder")}
          value={keepRaw}
          onChange={(e) => {
            setKeepRaw(e.target.value)
            const list = parseNameList(e.target.value)
            onParamsChange((p) => ({ ...p, keep_names: list }))
          }}
        />
      </div>
      <div className="space-y-1 sm:col-span-2">
        <Label htmlFor="mp-rs-notes">{t("translate.reskinNotes")}</Label>
        <Textarea
          id="mp-rs-notes"
          rows={2}
          maxLength={RESKIN_NOTES_MAX}
          placeholder={t("translate.reskinNotesPlaceholder")}
          value={notes}
          onChange={(e) => onParamsChange((p) => ({ ...p, notes: e.target.value }))}
        />
        <p className="text-xs text-muted-foreground">
          {notes.length}/{RESKIN_NOTES_MAX}
        </p>
      </div>
    </>
  )
}
