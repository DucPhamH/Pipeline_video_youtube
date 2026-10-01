import type { ComponentType } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { AlertTriangle, ArrowRight, BookCheck, Radar } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import type { Novel } from "../../../api/types"
import { crawlApi } from "../api"
import { Skeleton } from "@/components/Skeleton"

type Tone = "collect" | "success" | "danger"

const TONE: Record<Tone, { box: string; icon: string; cta: string }> = {
  collect: {
    box: "bg-stage-collect-soft/70 ring-stage-collect/15",
    icon: "bg-card text-stage-collect",
    cta: "text-stage-collect",
  },
  success: {
    box: "bg-success-soft/70 ring-success/15",
    icon: "bg-card text-success",
    cta: "text-accent-foreground",
  },
  danger: {
    box: "bg-danger-soft/70 ring-danger/15",
    icon: "bg-card text-danger",
    cta: "text-danger",
  },
}

/** Bảng "Hôm nay": 3 cột màu — đang crawl (live) / sẵn sàng xử lý / lỗi cần sửa. */
export function TodayQueue() {
  const t = useT()

  const ready = useQuery({
    queryKey: ["novels", "today-queue", "fully_crawled"],
    queryFn: () => crawlApi.listNovels({ status: "fully_crawled", limit: 4, offset: 0 }),
  })
  const errors = useQuery({
    queryKey: ["novels", "today-queue", "error"],
    queryFn: () => crawlApi.listNovels({ status: "error", limit: 4, offset: 0 }),
  })
  const crawling = useQuery({
    queryKey: ["novels", "today-queue", "crawling"],
    queryFn: () => crawlApi.listNovels({ status: "crawling", limit: 4, offset: 0 }),
    refetchInterval: (q) => ((q.state.data?.total ?? 0) > 0 ? 4000 : false),
  })

  const loading = ready.isLoading || errors.isLoading || crawling.isLoading

  return (
    <section aria-labelledby="today-title" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="today-title" className="text-[17px] font-semibold">
          {t("today.title")}
        </h2>
        <p className="text-sm text-muted-foreground">{t("today.hint")}</p>
      </div>
      {loading ? (
        <div className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 rounded-2xl" />
          ))}
        </div>
      ) : (
        <div className="stagger grid gap-3 md:grid-cols-3">
          <QueueColumn
            tone="collect"
            icon={Radar}
            live={(crawling.data?.total ?? 0) > 0}
            label={t("today.crawling")}
            hint={t("today.crawlingHint")}
            count={crawling.data?.total ?? 0}
            empty={t("today.emptyCrawling")}
            items={crawling.data?.items ?? []}
            actionLabel={t("today.view")}
            showProgress
          />
          <QueueColumn
            tone="success"
            icon={BookCheck}
            label={t("today.ready")}
            hint={t("today.readyHint")}
            count={ready.data?.total ?? 0}
            empty={t("today.emptyReady")}
            items={ready.data?.items ?? []}
            actionLabel={t("today.open")}
          />
          <QueueColumn
            tone="danger"
            icon={AlertTriangle}
            label={t("today.errors")}
            hint={t("today.errorsHint")}
            count={errors.data?.total ?? 0}
            empty={t("today.emptyErrors")}
            items={errors.data?.items ?? []}
            actionLabel={t("today.fix")}
            showError
          />
        </div>
      )}
    </section>
  )
}

function QueueColumn({
  tone,
  icon: Icon,
  live = false,
  label,
  hint,
  count,
  empty,
  items,
  actionLabel,
  showProgress = false,
  showError = false,
}: {
  tone: Tone
  icon: ComponentType<{ className?: string }>
  live?: boolean
  label: string
  hint: string
  count: number
  empty: string
  items: Novel[]
  actionLabel: string
  showProgress?: boolean
  showError?: boolean
}) {
  const t = useT()
  const s = TONE[tone]
  return (
    <div className={cn("flex min-w-0 flex-col gap-3 rounded-2xl p-4 ring-1", s.box)}>
      <div className="flex items-start gap-3">
        <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm", s.icon)}>
          <Icon className="size-[18px]" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-semibold">
            {label}
            {live ? <span aria-hidden className="dot-live size-1.5 rounded-full bg-live" /> : null}
          </p>
          <p className="text-[13px] leading-snug text-muted-foreground">{hint}</p>
        </div>
        <span className="font-mono text-[28px] leading-none font-medium tabular-nums">{count}</span>
      </div>
      {items.length === 0 ? (
        <p className="rounded-xl bg-card/60 px-3 py-2.5 text-[13px] text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((n) => {
            const done = n.crawled_chapters ?? n.last_chapter_index
            const pct = n.total_chapters ? (done / n.total_chapters) * 100 : null
            return (
              <li key={n.id}>
                <Link
                  to={`/novels/${n.id}`}
                  className="group flex items-center gap-3 rounded-xl bg-card px-3 py-2 shadow-[0_1px_2px_rgb(16_22_20/0.05)] transition-colors hover:bg-card/80 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="truncate text-sm font-medium">{n.title}</p>
                    {showProgress ? (
                      <div className="flex items-center gap-2">
                        <Progress value={pct} tone="collect" live size="sm" className="flex-1" />
                        <span className="shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                          {done}/{n.total_chapters ?? "?"}
                        </span>
                      </div>
                    ) : showError && n.error_message ? (
                      <p className="truncate text-xs text-danger" title={n.error_message}>
                        {n.error_message}
                      </p>
                    ) : (
                      <p className="truncate text-xs text-muted-foreground">{n.source_key}</p>
                    )}
                  </div>
                  <span className={cn("inline-flex shrink-0 items-center gap-1 text-[13px] font-semibold", s.cta)}>
                    {actionLabel}
                    <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
      {count > items.length ? (
        <p className="mt-auto text-xs text-muted-foreground">{t("today.more", { count: count - items.length })}</p>
      ) : null}
    </div>
  )
}
