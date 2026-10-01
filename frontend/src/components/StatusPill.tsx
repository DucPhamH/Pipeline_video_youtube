import { Badge } from "@/components/ui/badge"
import { useT } from "@/i18n"
import { isLiveStatus, statusTone, type StatusTone } from "./status"

export type { StatusTone }

/**
 * Viên trạng thái chuẩn cho mọi job/việc. Nhãn mặc định lấy từ `status.<key>`
 * trong i18n; truyền `label` để ghi đè. Trạng thái đang chạy có chấm nhịp thở.
 */
export function StatusPill({
  status,
  label,
  tone,
  live,
  className,
}: {
  status: string | null | undefined
  label?: string
  tone?: StatusTone
  live?: boolean
  className?: string
}) {
  const t = useT()
  const key = (status ?? "").toLowerCase()
  const resolvedTone = tone ?? statusTone(key)
  const isLive = live ?? isLiveStatus(key)
  const i18nKey = `status.${key}`
  const translated = t(i18nKey)
  const text = label ?? (translated === i18nKey ? status ?? "—" : translated)
  return (
    <Badge variant={resolvedTone} live={isLive} dot={!isLive && resolvedTone !== "neutral"} className={className}>
      {text}
    </Badge>
  )
}
