import type { ReactNode } from "react"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

/**
 * Một dòng cài đặt: nhãn + mô tả bên trái, ô nhập bên phải (desktop);
 * xếp chồng trên mobile. Dùng chung cho Settings / Scan settings.
 */
export function SettingRow({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: ReactNode
  hint?: ReactNode
  htmlFor?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "grid gap-2 py-4 first:pt-0 last:pb-0 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:gap-6",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        <Label htmlFor={htmlFor} className="text-sm font-semibold">
          {label}
        </Label>
        {hint ? <p className="text-[13px] leading-snug text-muted-foreground">{hint}</p> : null}
      </div>
      <div className="min-w-0 md:pt-0.5">{children}</div>
    </div>
  )
}

/** Nhóm cài đặt: tiêu đề + mô tả, các SettingRow phân cách bằng vạch mảnh. */
export function SettingGroup({
  title,
  description,
  icon,
  children,
  className,
}: {
  title: ReactNode
  description?: ReactNode
  icon?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn("space-y-4", className)}>
      <div className="flex items-start gap-3">
        {icon ? (
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-stage-collect-soft text-stage-collect">
            {icon}
          </span>
        ) : null}
        <div className="min-w-0 space-y-0.5">
          <h3 className="text-[15px] font-semibold">{title}</h3>
          {description ? <p className="text-[13px] leading-snug text-muted-foreground">{description}</p> : null}
        </div>
      </div>
      <div className="divide-y divide-border">{children}</div>
    </section>
  )
}
