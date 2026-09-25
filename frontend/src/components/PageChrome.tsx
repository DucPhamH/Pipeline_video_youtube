import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export function PageShell({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={cn("space-y-6", className)}>{children}</div>
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  const hasHeader = title != null || description != null || actions != null
  return (
    <Card className={className}>
      {hasHeader ? (
        <CardHeader className="border-b [.border-b]:pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              {title != null ? <CardTitle className="font-heading text-[1.05rem]">{title}</CardTitle> : null}
              {description != null ? <CardDescription>{description}</CardDescription> : null}
            </div>
            {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
          </div>
        </CardHeader>
      ) : null}
      <CardContent className={hasHeader ? undefined : "pt-1"}>{children}</CardContent>
    </Card>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0 space-y-1.5">
        {eyebrow ? <div className="text-xs text-muted-foreground">{eyebrow}</div> : null}
        <h1 className="font-heading text-2xl tracking-tight text-balance sm:text-[1.65rem]">{title}</h1>
        {description ? (
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function SegmentedTabs<T extends string>({
  value,
  onChange,
  items,
  className,
}: {
  value: T
  onChange: (value: T) => void
  items: Array<{ value: T; label: string }>
  className?: string
}) {
  return (
    <div
      role="tablist"
      className={cn("inline-flex flex-wrap gap-1 rounded-xl bg-muted p-1", className)}
    >
      {items.map((item) => {
        const active = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={cn(
              "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-card text-foreground shadow-sm ring-1 ring-border"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}

export function Toolbar({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={cn("flex flex-wrap items-center gap-3", className)}>{children}</div>
}

export function StatChip({
  label,
  value,
  tone = "default",
}: {
  label: string
  value: ReactNode
  tone?: "default" | "success" | "warn"
}) {
  return (
    <div
      className={cn(
        "rounded-lg px-3 py-2 ring-1",
        tone === "success" && "bg-emerald-500/8 ring-emerald-500/20",
        tone === "warn" && "bg-amber-500/8 ring-amber-500/20",
        tone === "default" && "bg-muted/50 ring-border",
      )}
    >
      <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums tracking-tight">{value}</p>
    </div>
  )
}
