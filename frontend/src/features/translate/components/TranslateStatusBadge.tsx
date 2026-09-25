/** Badge màu cho status job/segment — cùng phong cách với crawl's StatusBadge. */
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const STYLES: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  queued: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  running: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  completed: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  done: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  skipped_cache: "bg-teal-500/10 text-teal-700 dark:text-teal-300",
  failed: "bg-red-500/10 text-red-700 dark:text-red-300",
  cancelled: "bg-muted text-muted-foreground",
}

export function TranslateStatusBadge({ status, label }: { status: string; label: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("border-transparent font-medium", STYLES[status] ?? "bg-muted text-muted-foreground")}
    >
      {label}
    </Badge>
  )
}
