import { cn } from "cn"

export type ProgressTone = "primary" | "live" | "collect" | "translate" | "listen" | "write" | "glow" | "danger"

const TONE: Record<ProgressTone, string> = {
  primary: "bg-primary",
  live: "bg-live",
  glow: "bg-glow",
  collect: "bg-stage-collect",
  translate: "bg-stage-translate",
  listen: "bg-stage-listen",
  write: "bg-stage-write",
  danger: "bg-destructive",
}

/**
 * Thanh tiến độ. `value` 0–100 (null/undefined = chưa biết → thanh chạy vô định).
 * `live` thêm vệt sáng quét qua cho việc đang chạy.
 */
export function Progress({
  value,
  tone = "primary",
  live = false,
  size = "md",
  className,
  trackClassName,
  label,
}: {
  value?: number | null
  tone?: ProgressTone
  live?: boolean
  size?: "sm" | "md"
  className?: string
  /** Ghi đè màu nền rãnh (vd. trên nền tối của sidebar). */
  trackClassName?: string
  /** Nhãn cho trình đọc màn hình. */
  label?: string
}) {
  const known = typeof value === "number" && Number.isFinite(value)
  const pct = known ? Math.max(0, Math.min(100, value)) : 35
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={known ? Math.round(pct) : undefined}
      className={cn(
        "relative w-full overflow-hidden rounded-full bg-track",
        size === "sm" ? "h-1" : "h-2",
        trackClassName,
        className,
      )}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-500 ease-[cubic-bezier(.2,.8,.2,1)]",
          TONE[tone],
          (live || !known) && "progress-live",
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
