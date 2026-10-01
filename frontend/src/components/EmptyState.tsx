import type { ComponentType, ReactNode } from "react"
import { cn } from "@/lib/utils"

export type EmptyTone = "primary" | "collect" | "translate" | "listen" | "write" | "neutral"

const TONE: Record<EmptyTone, string> = {
  primary: "bg-accent text-accent-foreground",
  translate: "bg-stage-translate-soft text-stage-translate",
  collect: "bg-stage-collect-soft text-stage-collect",
  listen: "bg-stage-listen-soft text-stage-listen",
  write: "bg-stage-write-soft text-stage-write",
  neutral: "bg-muted text-muted-foreground",
}

/** Trạng thái rỗng: biểu tượng trong vòng tròn nhạt, tiêu đề, gợi ý, nút hành động. */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
  tone = "primary",
  compact = false,
  className,
}: {
  icon?: ComponentType<{ className?: string }>
  title: ReactNode
  hint?: ReactNode
  /** Thường là một <Button>. */
  action?: ReactNode
  tone?: EmptyTone
  compact?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        "rise flex flex-col items-center justify-center text-center",
        compact ? "gap-2 px-4 py-8" : "gap-3 px-6 py-14",
        className,
      )}
    >
      {Icon ? (
        <div className={cn("flex items-center justify-center rounded-full", compact ? "size-11" : "size-14", TONE[tone])}>
          <Icon className={compact ? "size-5" : "size-6"} aria-hidden />
        </div>
      ) : null}
      <p className={cn("font-semibold text-foreground", compact ? "text-[15px]" : "text-[17px]")}>{title}</p>
      {hint ? <p className="max-w-md text-sm text-muted-foreground">{hint}</p> : null}
      {action ? <div className="mt-2 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  )
}
