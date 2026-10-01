import type { ComponentType, KeyboardEvent, ReactNode } from "react"
import { Link } from "react-router-dom"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { useT } from "@/i18n"
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
              {title != null ? <CardTitle>{title}</CardTitle> : null}
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

export type Crumb = { label: ReactNode; to?: string }

export type StageTone = "collect" | "translate" | "listen" | "write"

const STAGE_TEXT: Record<StageTone, string> = {
  collect: "text-stage-collect",
  translate: "text-stage-translate",
  listen: "text-stage-listen",
  write: "text-stage-write",
}

/** Hàng breadcrumb nhỏ phía trên tiêu đề trang. Mục cuối là trang hiện tại. */
export function Breadcrumbs({ items, className }: { items: Crumb[]; className?: string }) {
  const t = useT()
  if (items.length === 0) return null
  return (
    <nav aria-label={t("shell.breadcrumb")} className={cn("flex min-w-0 flex-wrap items-center gap-1.5 text-[13px] text-muted-foreground", className)}>
      {items.map((c, i) => {
        const last = i === items.length - 1
        return (
          <span key={i} className="flex min-w-0 items-center gap-1.5">
            {c.to && !last ? (
              <Link to={c.to} className="truncate rounded-sm transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none">
                {c.label}
              </Link>
            ) : (
              <span className={cn("truncate", last && "font-semibold text-foreground")} aria-current={last ? "page" : undefined}>
                {c.label}
              </span>
            )}
            {!last ? <ChevronRight className="size-3.5 shrink-0 opacity-60" aria-hidden /> : null}
          </span>
        )
      })}
    </nav>
  )
}

/**
 * Đầu trang chuẩn: breadcrumb → eyebrow → tiêu đề (Fraunces) + meta/mô tả,
 * bên phải: hành động phụ rồi MỘT hành động chính (luôn ở góc phải trên).
 * Hành động phá huỷ để trong ActionMenu (overflow), không đặt ở đây.
 * `actions` (cũ) vẫn được hỗ trợ — hiển thị cùng chỗ với secondaryActions.
 */
export function PageHeader({
  breadcrumbs,
  eyebrow,
  stage,
  title,
  meta,
  description,
  secondaryActions,
  primaryAction,
  actions,
  tabs,
  className,
}: {
  breadcrumbs?: Crumb[]
  eyebrow?: ReactNode
  /** Tô màu eyebrow theo bước pipeline. */
  stage?: StageTone
  title: ReactNode
  /** Dòng phụ ngắn ngay dưới tiêu đề (số chương, ngôn ngữ, StatusPill…). */
  meta?: ReactNode
  description?: ReactNode
  secondaryActions?: ReactNode
  primaryAction?: ReactNode
  /** @deprecated dùng primaryAction + secondaryActions. */
  actions?: ReactNode
  /** Thường là <SegmentedTabs variant="underline" />, nằm sát đáy header. */
  tabs?: ReactNode
  className?: string
}) {
  const hasActions = actions != null || secondaryActions != null || primaryAction != null
  return (
    <header className={cn("space-y-4", className)}>
      {breadcrumbs?.length ? <Breadcrumbs items={breadcrumbs} /> : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          {eyebrow ? (
            <div
              className={cn(
                "text-xs font-semibold tracking-[0.1em] uppercase",
                stage ? STAGE_TEXT[stage] : "text-muted-foreground",
              )}
            >
              {eyebrow}
            </div>
          ) : null}
          <h1 className="font-display text-[30px] leading-[1.1] text-balance sm:text-[36px]">{title}</h1>
          {meta ? <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted-foreground">{meta}</div> : null}
          {description ? (
            <p className="max-w-3xl text-[15px] leading-relaxed text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {hasActions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end sm:pt-1">
            {actions}
            {secondaryActions}
            {primaryAction}
          </div>
        ) : null}
      </div>
      {tabs ? <div className="-mb-px">{tabs}</div> : null}
    </header>
  )
}

export type TabItem<T extends string> = {
  value: T
  label: ReactNode
  count?: number
  icon?: ComponentType<{ className?: string }>
}

/**
 * Tabs. `segmented` (mặc định, viên bo trên nền muted) cho bộ lọc nhỏ;
 * `underline` cho tab cấp trang (nằm dưới PageHeader, có vạch dưới).
 */
export function SegmentedTabs<T extends string>({
  value,
  onChange,
  items,
  variant = "segmented",
  className,
}: {
  value: T
  onChange: (value: T) => void
  items: Array<TabItem<T>>
  variant?: "segmented" | "underline"
  className?: string
}) {
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return
    const i = items.findIndex((it) => it.value === value)
    if (i < 0) return
    const next = items[(i + (e.key === "ArrowRight" ? 1 : items.length - 1)) % items.length]
    onChange(next.value)
    const el = e.currentTarget.querySelector<HTMLButtonElement>(`[data-value="${CSS.escape(next.value)}"]`)
    el?.focus()
  }
  const underline = variant === "underline"
  return (
    <div
      role="tablist"
      onKeyDown={onKeyDown}
      className={cn(
        underline
          ? "scrollbar-thin flex gap-1 overflow-x-auto overflow-y-hidden border-b border-border"
          : "inline-flex flex-wrap gap-1 rounded-xl bg-muted p-1",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.value === value
        const Icon = item.icon
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            data-value={item.value}
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(item.value)}
            className={cn(
              "inline-flex shrink-0 items-center gap-2 text-sm font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              underline
                ? cn(
                    "relative h-11 rounded-t-md px-3 after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:transition-colors",
                    active
                      ? "font-semibold text-foreground after:bg-primary"
                      : "text-muted-foreground after:bg-transparent hover:text-foreground",
                  )
                : cn(
                    "rounded-lg px-3.5 py-1.5",
                    active
                      ? "bg-card text-foreground shadow-sm ring-1 ring-border"
                      : "text-muted-foreground hover:text-foreground",
                  ),
            )}
          >
            {Icon ? <Icon className="size-4" /> : null}
            {item.label}
            {item.count != null ? (
              <span
                className={cn(
                  "rounded-full px-1.5 py-px font-mono text-[11px] tabular-nums",
                  active ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground",
                )}
              >
                {item.count}
              </span>
            ) : null}
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
        "rounded-xl px-3.5 py-2.5 ring-1",
        tone === "success" && "bg-success-soft ring-success/20",
        tone === "warn" && "bg-warning-soft ring-warning/20",
        tone === "default" && "bg-card ring-border",
      )}
    >
      <p className="text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
        {label}
      </p>
      <p className="mt-0.5 font-mono text-xl font-medium tabular-nums tracking-tight">{value}</p>
    </div>
  )
}
