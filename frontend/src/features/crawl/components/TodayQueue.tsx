import type { ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { SectionCard } from "@/components/PageChrome"
import { crawlApi } from "../api"

/** Hàng đợi việc hôm nay — không phải full history audit. */
export function TodayQueue() {
  const t = useT()

  const ready = useQuery({
    queryKey: ["novels", "today-queue", "fully_crawled"],
    queryFn: () => crawlApi.listNovels({ status: "fully_crawled", limit: 5, offset: 0 }),
  })
  const errors = useQuery({
    queryKey: ["novels", "today-queue", "error"],
    queryFn: () => crawlApi.listNovels({ status: "error", limit: 5, offset: 0 }),
  })
  const crawling = useQuery({
    queryKey: ["novels", "today-queue", "crawling"],
    queryFn: () => crawlApi.listNovels({ status: "crawling", limit: 5, offset: 0 }),
    refetchInterval: (q) => ((q.state.data?.total ?? 0) > 0 ? 4000 : false),
  })

  const readyTotal = ready.data?.total ?? 0
  const errorTotal = errors.data?.total ?? 0
  const crawlingTotal = crawling.data?.total ?? 0
  const loading = ready.isLoading || errors.isLoading || crawling.isLoading

  if (loading) {
    return (
      <Card>
        <CardContent className="py-4 text-sm text-muted-foreground">{t("app.loading")}</CardContent>
      </Card>
    )
  }

  if (readyTotal === 0 && errorTotal === 0 && crawlingTotal === 0) {
    return null
  }

  return (
    <SectionCard title={t("today.title")} description={t("today.hint")}>
        <div className="grid gap-3 sm:grid-cols-3">
          <QueueColumn
            icon={<Loader2 className="size-3.5" />}
            label={t("today.crawling")}
            count={crawlingTotal}
            empty={t("today.emptyCrawling")}
            items={(crawling.data?.items ?? []).map((n) => ({
              id: n.id,
              title: n.title,
              meta: n.source_key,
            }))}
          />
          <QueueColumn
            icon={<CheckCircle2 className="size-3.5" />}
            label={t("today.ready")}
            count={readyTotal}
            empty={t("today.emptyReady")}
            tone="success"
            items={(ready.data?.items ?? []).map((n) => ({
              id: n.id,
              title: n.title,
              meta: n.source_key,
            }))}
            actionLabel={t("today.open")}
          />
          <QueueColumn
            icon={<AlertCircle className="size-3.5" />}
            label={t("today.errors")}
            count={errorTotal}
            empty={t("today.emptyErrors")}
            tone="warn"
            items={(errors.data?.items ?? []).map((n) => ({
              id: n.id,
              title: n.title,
              meta: n.source_key,
            }))}
            actionLabel={t("today.fix")}
          />
        </div>
    </SectionCard>
  )
}

function QueueColumn({
  icon,
  label,
  count,
  empty,
  items,
  tone = "default",
  actionLabel,
}: {
  icon: ReactNode
  label: string
  count: number
  empty: string
  items: Array<{ id: number; title: string; meta: string }>
  tone?: "default" | "success" | "warn"
  actionLabel?: string
}) {
  const t = useT()
  return (
    <div
      className={cn(
        "rounded-lg p-3 ring-1",
        tone === "success" && "bg-emerald-500/5 ring-emerald-500/15",
        tone === "warn" && "bg-amber-500/5 ring-amber-500/15",
        tone === "default" && "bg-muted/40 ring-border",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          {icon}
          {label}
        </span>
        <span className="text-sm font-semibold tabular-nums">{count}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <Link
                  to={`/novels/${item.id}`}
                  className="block truncate text-sm font-medium hover:underline"
                >
                  {item.title}
                </Link>
                <p className="truncate text-[11px] text-muted-foreground">{item.meta}</p>
              </div>
              {actionLabel ? (
                <Link
                  to={`/novels/${item.id}`}
                  className={cn(
                    buttonVariants({ variant: "ghost", size: "sm" }),
                    "h-7 shrink-0 px-2 text-xs",
                  )}
                >
                  {actionLabel}
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {count > items.length ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          {t("today.more", { count: count - items.length })}
        </p>
      ) : null}
    </div>
  )
}
