import { Badge } from "@/components/ui/badge"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import type { LifecycleStatus } from "../../../api/types"

const STYLES: Record<LifecycleStatus, string> = {
  discovered: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  crawling: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  fully_crawled: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  translating: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  ready_for_video: "bg-teal-500/10 text-teal-700 dark:text-teal-300",
  produced: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-200",
  rejected: "bg-muted text-muted-foreground",
  error: "bg-red-500/10 text-red-700 dark:text-red-300",
}

export function StatusBadge({ status }: { status: LifecycleStatus }) {
  const t = useT()
  return (
    <Badge variant="outline" className={cn("border-transparent font-medium", STYLES[status])}>
      {t(`lifecycle.${status}`) || status}
    </Badge>
  )
}
