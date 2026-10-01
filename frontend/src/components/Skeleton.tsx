import { useT } from "@/i18n"
import { cn } from "@/lib/utils"

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton-shimmer rounded-md", className)} />
}

/** Khung hàng chờ dữ liệu của một danh sách. */
export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  const t = useT()
  return (
    <div role="status" className="space-y-3">
      <span className="sr-only">{t("app.loading")}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="space-y-1.5">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-1/4" />
        </div>
      ))}
    </div>
  )
}

/** Khung cả trang: tiêu đề, mô tả, rồi hai khối nội dung. */
export function PageSkeleton({ withHeader = true }: { withHeader?: boolean }) {
  const t = useT()
  return (
    <div role="status" className="space-y-6">
      <span className="sr-only">{t("app.loading")}</span>
      {withHeader ? (
        <div className="space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-72 max-w-full" />
          <Skeleton className="h-4 w-48" />
        </div>
      ) : null}
      <Skeleton className="h-40 w-full rounded-[16px]" />
      <Skeleton className="h-64 w-full rounded-[16px]" />
    </div>
  )
}
