import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { ChevronRightIcon, Search } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { PageHeader, PageShell, SegmentedTabs, Toolbar } from "@/components/PageChrome"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import type {
  Site,
  SiteAccessFilter,
  SiteAccessKind,
  SiteRegion,
  SiteRegionFilter,
} from "../../../api/types"
import { crawlApi } from "../api"
import { getSessionGuide } from "../sessionGuides"
import { TodayQueue } from "../components/TodayQueue"

const PAGE_SIZE = 10

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

  const regionLabel = (r: SiteRegion | SiteRegionFilter) => t(`region.${r}`)
  const accessLabel = (a: SiteAccessFilter) => t(`access.${a}`)

  const accessBadge = useMemo(
    () =>
      ({
        free: null,
        session_optional: {
          label: t("access.badgeOptional"),
          className: "border-amber-500/30 text-amber-800 dark:text-amber-300",
        },
        session_required: {
          label: t("access.badgeRequired"),
          className: "border-rose-500/30 text-rose-800 dark:text-rose-300",
        },
      }) as Record<SiteAccessKind, { label: string; className?: string } | null>,
    [t],
  )

  useEffect(() => {
    setOffset(0)
  }, [debouncedSearch, regionTab, accessFilter])

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

  if (error && sites === null) {
    return (
      <PageShell>
        <PageHeader title={t("sites.title")} description={t("sites.pageDesc")} />
        <p className="text-sm text-destructive">{error}</p>
      </PageShell>
    )
  }
  if (sites === null) {
    return (
      <PageShell>
        <PageHeader title={t("sites.title")} description={t("sites.pageDesc")} />
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      </PageShell>
    )
  }

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)

  return (
    <PageShell>
      <PageHeader
        title={t("sites.title")}
        description={t("sites.pageDesc")}
        actions={
          total > 0 ? (
            <span className="text-sm text-muted-foreground">
              {t("common.range", { from, to, total })}
            </span>
          ) : null
        }
      />

      <TodayQueue />

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <SegmentedTabs
        value={regionTab}
        onChange={setRegionTab}
        items={REGION_VALUES.map((value) => ({ value, label: regionLabel(value) }))}
      />

      <Toolbar>
        <Select
          value={accessFilter}
          onValueChange={(v) => v && setAccessFilter(v as SiteAccessFilter)}
        >
          <SelectTrigger className="h-10 w-56">
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
        <div className="relative min-w-[16rem] flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            placeholder={t("sites.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-10 pl-9"
          />
        </div>
      </Toolbar>

      {sites.length === 0 && (
        <Alert>
          <AlertDescription>
            {debouncedSearch || regionTab !== "all" || accessFilter !== "all"
              ? t("sites.emptyFiltered")
              : t("sites.emptyNone")}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-2.5">
        {sites.map((site) => {
          const badge = accessBadge[site.access_kind]
          const guide = getSessionGuide(site.key)
          return (
            <Link key={site.key} to={`/sites/${site.key}`} className="group block">
              <Card className="flex flex-row items-center justify-between gap-4 px-4 py-3.5 transition-colors hover:bg-muted/40 group-focus-visible:ring-2 group-focus-visible:ring-ring">
                <div className="min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium tracking-tight">{site.name}</p>
                    <Badge variant="secondary" className="text-[10px] font-normal">
                      {regionLabel(site.region)}
                    </Badge>
                    {badge && (
                      <Badge
                        variant="outline"
                        className={`text-[10px] font-normal ${badge.className ?? ""}`}
                      >
                        {badge.label}
                      </Badge>
                    )}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    <span className="font-mono">{site.key}</span>
                    {guide ? <span className="hidden sm:inline"> — {guide.summary}</span> : null}
                  </p>
                </div>
                <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </Card>
            </Link>
          )
        })}
      </div>

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
    </PageShell>
  )
}
