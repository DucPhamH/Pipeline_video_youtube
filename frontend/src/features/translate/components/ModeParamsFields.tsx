/** Chọn Variant mode + form params riêng từng mode — dùng chung cho modal
 * "Bắt đầu dịch" (mục Nâng cao) và tab Variant trên Work page. */
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useT } from "@/i18n"
import type { StyleProfile } from "../types"

export const MODES = ["full", "pov", "audio_cut", "style_clone"] as const

export function defaultModeParams(mode: string): Record<string, unknown> {
  if (mode === "pov") return { target_pov: "first_person" }
  if (mode === "audio_cut") return { target_minutes: 10, max_chars: 12000, keep_dialogue_ratio: 0.7 }
  if (mode === "style_clone") return { style_profile_id: "web_novel_vn_shorts" }
  return {}
}

export function useModeLabel() {
  const t = useT()
  return (mode: string) => {
    if (mode === "pov") return t("translate.modePov")
    if (mode === "audio_cut") return t("translate.modeAudioCut")
    if (mode === "style_clone") return t("translate.modeStyleClone")
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
}

export function ModeParamsFields({
  mode,
  onModeChange,
  params,
  onParamsChange,
  styleProfiles,
  modes = MODES,
}: Props) {
  const t = useT()
  const modeLabel = useModeLabel()

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1">
        <Label htmlFor="mp-mode">{t("translate.variantMode")}</Label>
        <select
          id="mp-mode"
          className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
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
      </div>

      {mode === "pov" ? (
        <>
          <div className="space-y-1">
            <Label htmlFor="mp-pov">{t("translate.targetPov")}</Label>
            <select
              id="mp-pov"
              className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
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
            className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
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
    </div>
  )
}
