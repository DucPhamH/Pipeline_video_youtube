/** Diện mạo chung cho từng mode variant: icon, màu nền nhạt, nhãn ngắn và
 * tóm tắt params — dùng ở Book hub, modal Bắt đầu dịch và thư viện. */
import type { ComponentType } from "react"
import { BookOpenText, Eye, Feather, Scissors, Shirt } from "lucide-react"
import { useT } from "@/i18n"
import type { StyleProfile } from "../types"

export type ModeVisual = {
  icon: ComponentType<{ className?: string }>
  /** Lớp nền + chữ cho ô icon. */
  tint: string
  /** Tone của <Progress>. */
  tone: "translate" | "collect" | "listen" | "write" | "primary"
}

const VISUAL: Record<string, ModeVisual> = {
  full: { icon: BookOpenText, tint: "bg-stage-translate-soft text-stage-translate", tone: "translate" },
  pov: { icon: Eye, tint: "bg-stage-collect-soft text-stage-collect", tone: "collect" },
  audio_cut: { icon: Scissors, tint: "bg-stage-listen-soft text-stage-listen", tone: "listen" },
  style_clone: { icon: Feather, tint: "bg-stage-write-soft text-stage-write", tone: "write" },
  reskin: { icon: Shirt, tint: "bg-info-soft text-info", tone: "primary" },
}

export function modeVisual(mode: string): ModeVisual {
  return VISUAL[mode] ?? VISUAL.full
}

/** Nhãn ngắn, thân thiện (không có tiền tố enum như "pov — ..."). */
export function useModeTitle() {
  const t = useT()
  return (mode: string) => {
    if (mode === "pov") return t("translate.hub.modePov")
    if (mode === "audio_cut") return t("translate.hub.modeAudioCut")
    if (mode === "style_clone") return t("translate.hub.modeStyleClone")
    if (mode === "reskin") return t("translate.hub.modeReskin")
    return t("translate.hub.modeFull")
  }
}

/** Mô tả một dòng cho từng mode (dùng trong thẻ chọn mode). */
export function useModeBlurb() {
  const t = useT()
  return (mode: string) => {
    if (mode === "pov") return t("translate.hub.blurbPov")
    if (mode === "audio_cut") return t("translate.hub.blurbAudioCut")
    if (mode === "style_clone") return t("translate.hub.blurbStyleClone")
    if (mode === "reskin") return t("translate.hub.blurbReskin")
    return t("translate.hub.blurbFull")
  }
}

/** Tóm tắt params của 1 variant, vd "Ngôi thứ nhất · Lâm Phong" / "~10 phút". */
export function useParamsSummary(styleProfiles: StyleProfile[] = []) {
  const t = useT()
  return (mode: string, params: Record<string, unknown> | null | undefined, model?: string) => {
    const p = params ?? {}
    const parts: string[] = []
    if (mode === "full") {
      parts.push(t("translate.hub.faithful"))
    } else if (mode === "pov") {
      const pov = String(p.target_pov || "first_person")
      parts.push(
        pov === "third_person"
          ? t("translate.povThird")
          : pov === "second_person"
            ? t("translate.povSecond")
            : t("translate.povFirst"),
      )
      if (p.viewpoint_character) parts.push(String(p.viewpoint_character))
    } else if (mode === "audio_cut") {
      parts.push(t("translate.hub.minutesPerChapter", { n: Number(p.target_minutes) || 10 }))
    } else if (mode === "style_clone") {
      const id = String(p.style_profile_id || "")
      parts.push(styleProfiles.find((s) => s.id === id)?.label || id || "—")
    } else if (mode === "reskin") {
      const setting = String(p.setting || "modern_urban")
      parts.push(
        setting === "custom" && p.custom_setting
          ? String(p.custom_setting).slice(0, 40)
          : t(`translate.reskinSetting_${setting}`),
      )
      parts.push(t(`translate.reskinIntensity_${String(p.intensity || "medium")}`))
    }
    if (p.polish) parts.push(t("translate.hub.polishShort"))
    if (model) parts.push(model)
    return parts.join(" · ")
  }
}
