import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useParams } from "react-router-dom"
import { KeyRound, Library, Link2, Radar, Settings2 } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { PageHeader, PageShell, SegmentedTabs } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { queryKeys } from "@/lib/query-client"
import { crawlApi } from "../api"
import { AddNovelForm } from "../components/AddNovelForm"
import { GenreScanCard } from "../components/GenreScanCard"
import { useGenreScan } from "../components/useGenreScan"
import { SessionStatusPill, SiteSessionDialog } from "../components/SiteSessionDialog"
import { useSiteSession } from "../components/useSiteSession"
import { SiteSettingsDialog } from "../components/SiteSettingsDialog"
import { SiteLibrary } from "../components/SiteLibrary"
import { getSessionGuide } from "../sessionGuides"

// Trang chi tiết 1 SITE — Quét / URL / Thư viện.
const POLL_INTERVAL_MS = 3000

type CrawlTab = "bulk" | "url" | "library"

export function SiteDetailPage() {
  const t = useT()
  const { sourceKey = "" } = useParams<{ sourceKey: string }>()
  const [tab, setTab] = useState<CrawlTab>("bulk")
  const [sessionOpen, setSessionOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [libraryVisited, setLibraryVisited] = useState(false)
  if (tab === "library" && !libraryVisited) setLibraryVisited(true)

  const { data: sitesData } = useQuery({
    queryKey: queryKeys.sites({ limit: 100 }),
    queryFn: () => crawlApi.listSites({ limit: 100 }),
  })
  const site = sitesData?.items.find((s) => s.key === sourceKey)
  const siteName = site?.name ?? sourceKey
  const sessionGuide = getSessionGuide(sourceKey)
  const { data: session } = useSiteSession(sourceKey)
  const scan = useGenreScan(sourceKey)

  const { data: libraryMeta } = useQuery({
    queryKey: ["novels", "library-meta", sourceKey],
    queryFn: async () => {
      const [all, errors, crawling] = await Promise.all([
        crawlApi.listNovels({ sourceKey, limit: 1, offset: 0 }),
        crawlApi.listNovels({ sourceKey, status: "error", limit: 1, offset: 0 }),
        crawlApi.listNovels({ sourceKey, status: "crawling", limit: 1, offset: 0 }),
      ])
      return { total: all.total, errors: errors.total, crawling: crawling.total }
    },
    // Đếm thay đổi khi đang crawl (truyện mới/lỗi mới) — lỗi cũ đứng yên thì không cần poll.
    refetchInterval: (q) => ((q.state.data?.crawling ?? 0) > 0 ? POLL_INTERVAL_MS : false),
  })

  const hints: Record<CrawlTab, string> = {
    bulk: t("site.bulkHint"),
    url: t("site.urlHint"),
    library: t("site.libraryHint"),
  }

  return (
    <PageShell>
      <PageHeader
        breadcrumbs={[{ label: t("sites.title"), to: "/sites" }, { label: siteName }]}
        eyebrow={t("sites.eyebrow")}
        stage="collect"
        title={siteName}
        meta={
          <>
            {site ? <Badge variant="collect">{t(`region.${site.region}`)}</Badge> : null}
            <span className="font-mono text-[13px]">{sourceKey}</span>
            <SessionStatusPill sourceKey={sourceKey} />
            {libraryMeta ? (
              <span>
                <span className="font-mono text-foreground tabular-nums">{libraryMeta.total}</span>{" "}
                {t("sites.novelsLabel")}
                {libraryMeta.errors > 0 ? (
                  <span className="text-danger">
                    {" · "}
                    <span className="font-mono tabular-nums">{libraryMeta.errors}</span> {t("site.errorsLabel")}
                  </span>
                ) : null}
              </span>
            ) : null}
          </>
        }
        description={t("site.pageDesc")}
        secondaryActions={
          <>
            <Button type="button" variant="outline" onClick={() => setSessionOpen(true)}>
              <KeyRound className="size-4" />
              {t("site.sessionBtn")}
            </Button>
            <Button type="button" variant="outline" onClick={() => setSettingsOpen(true)}>
              <Settings2 className="size-4" />
              {t("site.settingsTitle")}
            </Button>
          </>
        }
        primaryAction={
          <Button
            type="button"
            disabled={scan.isRunning || !scan.active || scan.runPending}
            title={!scan.active ? t("site.genreNotSelectedYet") : undefined}
            onClick={() => {
              setTab("bulk")
              scan.run()
            }}
          >
            <Radar className="size-4" />
            {scan.isRunning ? t("site.scanning") : t("site.scanNow")}
          </Button>
        }
        tabs={
          <SegmentedTabs
            variant="underline"
            className="overflow-y-hidden"
            value={tab}
            onChange={setTab}
            items={[
              { value: "bulk", label: t("site.tabBulk"), icon: Radar },
              { value: "url", label: t("site.tabUrl"), icon: Link2 },
              { value: "library", label: t("site.tabLibraryName"), icon: Library, count: libraryMeta?.total },
            ]}
          />
        }
      />

      {sessionGuide && !session?.configured && (
        <Alert className="border-warning/25 bg-warning-soft px-4 py-3">
          <KeyRound className="text-warning" />
          <AlertTitle>{t("site.sessionAlert")}</AlertTitle>
          <AlertDescription className="text-foreground/80">
            {sessionGuide.summary}{" "}
            <button
              type="button"
              className="font-semibold text-accent-foreground underline-offset-2 hover:underline"
              onClick={() => setSessionOpen(true)}
            >
              {t("site.sessionGuideLink")}
            </button>
          </AlertDescription>
        </Alert>
      )}

      <p className="text-sm text-muted-foreground">{hints[tab]}</p>

      {tab === "bulk" ? <GenreScanCard scan={scan} /> : null}
      {tab === "url" ? <AddNovelForm sourceKey={sourceKey} /> : null}
      {/* Giữ thư viện mounted sau lần mở đầu để bộ lọc không mất khi đổi tab. */}
      {libraryVisited ? (
        <div hidden={tab !== "library"}>
          <SiteLibrary sourceKey={sourceKey} />
        </div>
      ) : null}

      <SiteSessionDialog sourceKey={sourceKey} open={sessionOpen} onOpenChange={setSessionOpen} />
      <SiteSettingsDialog sourceKey={sourceKey} open={settingsOpen} onOpenChange={setSettingsOpen} />
    </PageShell>
  )
}
