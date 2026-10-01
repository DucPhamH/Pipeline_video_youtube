import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowRight, Globe2, KeyRound, Library, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { PageHeader, PageShell, SegmentedTabs } from "@/components/PageChrome"
import { EmptyState } from "@/components/EmptyState"
import { StatusPill } from "@/components/StatusPill"
import { coverColors } from "@/components/coverColors"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { ApiError } from "../../../api/client"
import type { Genre, Site, SiteAccessFilter, SiteRegionFilter } from "../../../api/types"
import { crawlApi } from "../api"
import { getSessionGuide } from "../sessionGuides"
import { TodayQueue } from "../components/TodayQueue"
import { Skeleton } from "@/components/Skeleton"

const PAGE_SIZE = 12

const REGION_VALUES: SiteRegionFilter[] = ["all", "china", "japan", "korea", "vietnam", "taiwan"]
const ACCESS_VALUES: SiteAccessFilter[] = [
  "all",
  "free",
  "needs_session",
  "session_optional",
  "session_required",
]

export function SitesPage() {
  const t = useT()
  const [sites, setSites] = useState<Site[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [regionTab, setRegionTab] = useState<SiteRegionFilter>("all")
  const [accessFilter, setAccessFilter] = useState<SiteAccessFilter>("all")
  const [offset, setOffset] = useState(0)
  const debouncedSearch = useDebouncedValue(search.trim(), 350)

  const accessLabel = (a: SiteAccessFilter) => t(`access.${a}`)

  // Đổi bộ lọc → về trang đầu ngay trong render (không qua effect).
  const filterKey = `${debouncedSearch}|${regionTab}|${accessFilter}`
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey)
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey)
    setOffset(0)
  }

  useEffect(() => {
    let cancelled = false
    crawlApi
      .listSites({
        search: debouncedSearch || undefined,
        region: regionTab,
        accessKind: accessFilter,
        limit: PAGE_SIZE,
        offset,
      })
      .then((data) => {
        if (cancelled) return
        setError(null)
        setSites(data.items)
        setTotal(data.total)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : t("app.unknownError"))
      })
    return () => {
      cancelled = true
    }
  }, [debouncedSearch, regionTab, accessFilter, offset, t])

  // Đếm số site mỗi vùng (theo search + loại phiên hiện tại) cho nhãn tab.
  const { data: regionCounts } = useQuery({
    queryKey: ["sites", "region-counts", debouncedSearch, accessFilter],
    queryFn: async () => {
      const rows = await Promise.all(
        REGION_VALUES.map((region) =>
          crawlApi
            .listSites({ search: debouncedSearch || undefined, region, accessKind: accessFilter, limit: 1 })
            .then((d) => [region, d.total] as const),
        ),
      )
      return Object.fromEntries(rows) as Record<SiteRegionFilter, number>
    },
    staleTime: 60_000,
  })

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)
  const filtered = Boolean(debouncedSearch) || regionTab !== "all" || accessFilter !== "all"

  const header = (
    <PageHeader
      eyebrow={t("sites.eyebrow")}
      stage="collect"
      title={t("sites.title")}
      description={t("sites.pageDesc")}
    />
  )

  if (error && sites === null) {
    return (
      <PageShell>
        {header}
        <EmptyState icon={Globe2} tone="neutral" title={t("app.unknownError")} hint={error} />
      </PageShell>
    )
  }

  return (
    <PageShell>
      {header}

      <TodayQueue />

      <section aria-labelledby="sites-list-title" className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="sites-list-title" className="text-[17px] font-semibold">
            {t("sites.allSites")}
          </h2>
          {total > 0 ? (
            <span className="font-mono text-sm text-muted-foreground tabular-nums">
              {t("common.range", { from, to, total })}
            </span>
          ) : null}
        </div>

        <SegmentedTabs
          variant="underline"
          className="overflow-y-hidden"
          value={regionTab}
          onChange={setRegionTab}
          items={REGION_VALUES.map((value) => ({
            value,
            label: t(`region.${value}`),
            count: regionCounts?.[value],
          }))}
        />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              placeholder={t("sites.searchPlaceholder")}
              aria-label={t("sites.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-10 pl-9"
            />
          </div>
          <Select value={accessFilter} onValueChange={(v) => v && setAccessFilter(v as SiteAccessFilter)}>
            <SelectTrigger className="h-10 w-full sm:w-60" aria-label={t("sites.accessFilter")}>
              <SelectValue>{(v: string) => accessLabel(v as SiteAccessFilter)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {ACCESS_VALUES.map((value) => (
                <SelectItem key={value} value={value}>
                  {accessLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        {sites === null ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-40 rounded-2xl" />
            ))}
          </div>
        ) : sites.length === 0 ? (
          <div className="rounded-2xl border border-dashed bg-card">
            <EmptyState
              icon={Globe2}
              tone="collect"
              title={filtered ? t("sites.emptyFiltered") : t("sites.emptyNone")}
              hint={filtered ? t("sites.emptyFilteredHint") : undefined}
              action={
                filtered ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSearch("")
                      setRegionTab("all")
                      setAccessFilter("all")
                    }}
                  >
                    {t("sites.clearFilters")}
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {sites.map((site) => (
              <SiteCard key={site.key} site={site} />
            ))}
          </div>
        )}

        {total > PAGE_SIZE && (
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              {t("common.prev")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              {t("common.next")}
            </Button>
          </div>
        )}
      </section>
    </PageShell>
  )
}

/** Lượt quét gần nhất của site = thể loại đang chạy, hoặc thể loại xong muộn nhất. */
function latestRun(genres: Genre[]): Genre | null {
  const running = genres.find((g) => g.last_run_status === "running")
  if (running) return running
  let best: Genre | null = null
  for (const g of genres) {
    if (!g.last_run_finished_at) continue
    if (!best || (best.last_run_finished_at ?? "") < g.last_run_finished_at) best = g
  }
  return best
}

function formatShort(iso: string): string {
  try {
    const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`)
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
  } catch {
    return iso
  }
}

function SiteCard({ site }: { site: Site }) {
  const t = useT()
  const guide = getSessionGuide(site.key)
  const { bg } = coverColors(site.name)

  const { data: stats } = useQuery({
    queryKey: ["site-card", site.key],
    queryFn: async () => {
      const [novels, genres] = await Promise.all([
        crawlApi.listNovels({ sourceKey: site.key, limit: 1, offset: 0 }),
        crawlApi.listGenres({ sourceKey: site.key, limit: 100, offset: 0 }),
      ])
      return { novels: novels.total, last: latestRun(genres.items) }
    },
    staleTime: 60_000,
  })
  const { data: session } = useQuery({
    queryKey: ["site-session", site.key],
    queryFn: () => crawlApi.getSiteSession(site.key),
    enabled: site.access_kind !== "free",
    staleTime: 60_000,
  })

  const sessionPill =
    site.access_kind === "free" ? (
      <StatusPill status="free" tone="neutral" label={t("sites.sessionFree")} />
    ) : session?.configured ? (
      <StatusPill status="ready" tone="success" label={t("sites.sessionSaved")} />
    ) : (
      <StatusPill
        status="needs_session"
        tone={site.access_kind === "session_required" ? "warning" : "neutral"}
        label={site.access_kind === "session_required" ? t("access.badgeRequired") : t("access.badgeOptional")}
      />
    )

  const last = stats?.last ?? null

  return (
    <Link
      to={`/sites/${site.key}`}
      className="group flex flex-col gap-4 rounded-2xl border bg-card p-5 shadow-[0_1px_2px_rgb(16_22_20/0.04)] transition-[box-shadow,border-color,transform] hover:-translate-y-0.5 hover:border-stage-collect/30 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none motion-reduce:hover:translate-y-0"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="flex size-11 shrink-0 items-center justify-center rounded-xl font-display text-lg font-semibold text-white"
          style={{ backgroundColor: bg }}
        >
          {(site.name || site.key).slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold">{site.name}</p>
          <p className="truncate font-mono text-xs text-muted-foreground">{site.key}</p>
        </div>
        <Badge variant="collect">{t(`region.${site.region}`)}</Badge>
      </div>

      {guide ? <p className="line-clamp-2 text-[13px] leading-snug text-muted-foreground">{guide.summary}</p> : null}

      <div className="mt-auto flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground">
          <Library className="size-3.5" aria-hidden />
          {stats ? (
            <span className="font-mono text-foreground tabular-nums">{stats.novels}</span>
          ) : (
            <Skeleton className="h-3 w-5" />
          )}
          {t("sites.novelsLabel")}
        </span>
        <span aria-hidden className="text-border">
          •
        </span>
        <span className="inline-flex items-center gap-1.5">
          <KeyRound className="size-3.5 text-muted-foreground" aria-hidden />
          {sessionPill}
        </span>
      </div>

      <div className="flex items-center justify-between gap-2 border-t pt-3">
        <div className="flex min-w-0 items-center gap-2 text-[13px] text-muted-foreground">
          <span className="shrink-0">{t("sites.lastScan")}</span>
          {last ? (
            <>
              <StatusPill status={last.last_run_status} />
              {last.last_run_status !== "running" && last.last_run_finished_at ? (
                <span className="truncate font-mono text-xs">{formatShort(last.last_run_finished_at)}</span>
              ) : null}
            </>
          ) : stats ? (
            <span>{t("sites.neverScanned")}</span>
          ) : (
            <Skeleton className="h-3 w-16" />
          )}
        </div>
        <ArrowRight
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-stage-collect",
          )}
          aria-hidden
        />
      </div>
    </Link>
  )
}
