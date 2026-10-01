import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { BookOpen, LayoutGrid, MoreHorizontal, Rows3, Search } from "lucide-react"
import { toast } from "sonner"
import { Button, buttonVariants } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { BookCover } from "@/components/BookCover"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { EmptyState } from "@/components/EmptyState"
import { SegmentedTabs } from "@/components/PageChrome"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useT } from "@/i18n"
import { queryKeys } from "@/lib/query-client"
import { cn } from "@/lib/utils"
import { ApiError } from "../../../api/client"
import type { Genre, LifecycleStatus, Novel } from "../../../api/types"
import { crawlApi } from "../api"
import { StatusBadge } from "./StatusBadge"

// Danh sách truyện đã crawl của 1 site (từ "Quét ngay" HOẶC "Thêm bằng URL")
// — tự phân trang, lọc theo nguồn / thể loại / trạng thái / tên; xem dạng
// lưới bìa hoặc bảng (bảng thành danh sách thẻ trên mobile).

const POLL_INTERVAL_MS = 3000
const PAGE_SIZE = 12
const GENRE_SELECT_LIMIT = 100
const GENRE_FILTER_ALL = "__all__"
const VIEW_KEY = "crawl.libraryView"

type NovelOrigin = "all" | "scanned" | "manual"
type View = "grid" | "table"

const LIFECYCLE_STATUS_VALUES: Array<LifecycleStatus | "all"> = [
  "all",
  "discovered",
  "crawling",
  "fully_crawled",
  // translating / ready_for_video / produced — phase 2 (chưa ship) — không hiện filter
  "rejected",
  "error",
]

function canRecrawl(novel: Novel): boolean {
  // Nút Thử lại / Đồng bộ + chọn hàng loạt — rejected dùng "Buộc nhận" riêng.
  return novel.lifecycle_status === "error" || novel.lifecycle_status === "fully_crawled"
}

function canExportNovel(novel: Novel): boolean {
  return novel.lifecycle_status === "fully_crawled"
}

function canSelectNovel(novel: Novel): boolean {
  return canRecrawl(novel) || canExportNovel(novel)
}

function readView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "table" ? "table" : "grid"
  } catch {
    return "grid"
  }
}

export function SiteLibrary({ sourceKey }: { sourceKey: string }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [origin, setOrigin] = useState<NovelOrigin>("all")
  const [status, setStatus] = useState<LifecycleStatus | "all">("all")
  const [genreFilter, setGenreFilter] = useState<number | "all">("all")
  const [search, setSearch] = useState("")
  const [view, setViewState] = useState<View>(readView)
  const [offset, setOffset] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)

  const isManual = origin === "all" ? undefined : origin === "manual"

  function setView(v: View) {
    setViewState(v)
    try {
      localStorage.setItem(VIEW_KEY, v)
    } catch {
      /* bỏ qua — chỉ là tiện ích ghi nhớ */
    }
  }

  const statusOptions = useMemo(
    () => LIFECYCLE_STATUS_VALUES.map((value) => ({ value, label: t(`lifecycle.${value}`) })),
    [t],
  )
  const debouncedSearch = useDebouncedValue(search.trim(), 350)
  const effectiveStatus = status === "all" ? undefined : status
  const effectiveSearch = debouncedSearch || undefined
  const effectiveGenreId = isManual !== true && genreFilter !== "all" ? genreFilter : undefined

  const { data: genresData } = useQuery({
    queryKey: queryKeys.genres({ sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }),
    queryFn: () => crawlApi.listGenres({ sourceKey, limit: GENRE_SELECT_LIMIT }),
    enabled: isManual !== true,
  })
  const genreById = useMemo(() => {
    const map = new Map<number, Genre>()
    for (const g of genresData?.items ?? []) map.set(g.id, g)
    return map
  }, [genresData])

  // Đổi filter → về trang đầu NGAY TRONG RENDER, không qua effect (tránh 1
  // query thừa với offset CŨ — `react(set-state-in-effect)`).
  const filterKey = `${sourceKey}|${String(isManual)}|${effectiveStatus}|${effectiveGenreId}|${effectiveSearch}`
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey)
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey)
    setOffset(0)
  }
  // Xoá selection khi đổi filter HOẶC đổi trang.
  const selectionResetKey = `${filterKey}|${offset}`
  const [prevSelectionResetKey, setPrevSelectionResetKey] = useState(selectionResetKey)
  if (selectionResetKey !== prevSelectionResetKey) {
    setPrevSelectionResetKey(selectionResetKey)
    setSelectedIds(new Set())
  }

  const listParams = {
    sourceKey,
    status: effectiveStatus,
    search: effectiveSearch,
    isManual,
    genreId: effectiveGenreId,
    limit: PAGE_SIZE,
    offset,
  }

  const { data, error, isFetching } = useQuery({
    queryKey: queryKeys.novels(listParams),
    queryFn: () => crawlApi.listNovels(listParams),
    placeholderData: (prev) => prev,
    refetchInterval: (q) =>
      q.state.data?.items.some((n) => n.lifecycle_status === "crawling") ? POLL_INTERVAL_MS : false,
  })

  // Số truyện theo nguồn (cho nhãn tab con).
  const { data: originCounts } = useQuery({
    queryKey: ["novels", "origin-counts", sourceKey],
    queryFn: async () => {
      const [all, scanned, manual] = await Promise.all([
        crawlApi.listNovels({ sourceKey, limit: 1, offset: 0 }),
        crawlApi.listNovels({ sourceKey, isManual: false, limit: 1, offset: 0 }),
        crawlApi.listNovels({ sourceKey, isManual: true, limit: 1, offset: 0 }),
      ])
      return { all: all.total, scanned: scanned.total, manual: manual.total }
    },
  })

  const novels = data?.items ?? null
  const total = data?.total ?? 0
  const selectableOnPage = useMemo(() => (novels ?? []).filter(canSelectNovel), [novels])
  const allSelectableSelected =
    selectableOnPage.length > 0 && selectableOnPage.every((n) => selectedIds.has(n.id))
  const someSelectableSelected =
    selectableOnPage.some((n) => selectedIds.has(n.id)) && !allSelectableSelected
  const selectedRetryable = useMemo(
    () => (novels ?? []).filter((n) => selectedIds.has(n.id) && canRecrawl(n)),
    [novels, selectedIds],
  )
  const selectedExportable = useMemo(
    () => (novels ?? []).filter((n) => selectedIds.has(n.id) && canExportNovel(n)),
    [novels, selectedIds],
  )

  const errorCountParams = {
    sourceKey,
    status: "error" as const,
    isManual,
    genreId: effectiveGenreId,
    limit: 1,
    offset: 0,
  }
  const { data: errorCountData } = useQuery({
    queryKey: queryKeys.novels(errorCountParams),
    queryFn: () => crawlApi.listNovels(errorCountParams),
  })
  const errorTotal = errorCountData?.total ?? 0

  const onError = (err: unknown) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))

  const retryMutation = useMutation({
    mutationFn: (id: number) => crawlApi.retryNovel(id),
    onSuccess: () => {
      toast.message(t("site.toastRecrawl"))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError,
  })

  const forceMutation = useMutation({
    mutationFn: (id: number) => crawlApi.forceAcceptNovel(id),
    onSuccess: (result) => {
      if (!result.success) {
        toast.error(result.error ?? t("lifecycle.error"))
        return
      }
      toast.message(t("site.toastForce"))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError,
  })

  const deleteNovelMutation = useMutation({
    mutationFn: (id: number) => crawlApi.deleteNovel(id),
    onSuccess: () => {
      setConfirmDeleteId(null)
      toast.success(t("site.deleteOk"))
      setSelectedIds(new Set())
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError,
  })

  const retryAllErrorsMutation = useMutation({
    mutationFn: () =>
      crawlApi.retryErrorNovels({ sourceKey, isManual, genreId: effectiveGenreId, limit: 100 }),
    onSuccess: (result) => {
      setSelectedIds(new Set())
      if (result.queued > 0) toast.message(t("site.toastRetryQueued", { count: result.queued }))
      else toast.message(t("site.toastRetryNone"))
      if (result.skipped > 0) toast.error(t("site.toastSkipped", { count: result.skipped }))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError,
  })

  const bulkRecrawlMutation = useMutation({
    mutationFn: async (items: Novel[]) => {
      let ok = 0
      let fail = 0
      // Chỉ nhận novel error/fully_crawled (khớp canRecrawl()) — rejected
      // dùng "Buộc nhận" riêng từng dòng, KHÔNG qua action hàng loạt này.
      for (const novel of items) {
        try {
          await crawlApi.retryNovel(novel.id)
          ok += 1
        } catch {
          fail += 1
        }
      }
      return { ok, fail }
    },
    onSuccess: ({ ok, fail }) => {
      setSelectedIds(new Set())
      if (ok > 0) toast.message(t("site.toastRecrawlBatch", { count: ok }))
      if (fail > 0) toast.error(t("site.toastRecrawlFail", { count: fail }))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError,
  })

  const bulkExportMutation = useMutation({
    mutationFn: (ids: number[]) => crawlApi.exportNovelsBatch(ids, "bundle"),
    onSuccess: () => toast.success(t("site.exportBatchOk")),
    onError,
  })

  const bulkBusy = bulkRecrawlMutation.isPending || retryAllErrorsMutation.isPending
  const rowBusy =
    bulkRecrawlMutation.isPending ||
    bulkExportMutation.isPending ||
    retryAllErrorsMutation.isPending ||
    (retryMutation.isPending
      ? retryMutation.variables
      : forceMutation.isPending
        ? forceMutation.variables
        : null)

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)

  function toggleOne(id: number, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  function toggleAllOnPage(checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      for (const n of selectableOnPage) {
        if (checked) next.add(n.id)
        else next.delete(n.id)
      }
      return next
    })
  }

  const rowActions = (novel: Novel, compact = false) => (
    <NovelActions
      novel={novel}
      compact={compact}
      busy={rowBusy === novel.id}
      locked={bulkBusy}
      deletePending={deleteNovelMutation.isPending}
      onRetry={() => retryMutation.mutate(novel.id)}
      onForce={() => forceMutation.mutate(novel.id)}
      onDelete={() => setConfirmDeleteId(novel.id)}
    />
  )

  const genreLabel = (novel: Novel) =>
    novel.genre_id != null ? (genreById.get(novel.genre_id)?.label ?? `#${novel.genre_id}`) : "—"

  const hasFilters = status !== "all" || genreFilter !== "all" || Boolean(debouncedSearch)
  const selectedCount = selectedRetryable.length + selectedExportable.length

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedTabs
          value={origin}
          onChange={setOrigin}
          items={[
            { value: "all", label: t("site.originAll"), count: originCounts?.all },
            { value: "scanned", label: t("site.originScanned"), count: originCounts?.scanned },
            { value: "manual", label: t("site.originManual"), count: originCounts?.manual },
          ]}
        />
        <SegmentedTabs
          value={view}
          onChange={setView}
          items={[
            { value: "grid", label: <span className="sr-only sm:not-sr-only">{t("site.viewGrid")}</span>, icon: LayoutGrid },
            { value: "table", label: <span className="sr-only sm:not-sr-only">{t("site.viewTable")}</span>, icon: Rows3 },
          ]}
        />
      </div>

      {/* Thanh lọc */}
      <div className="flex flex-col gap-2.5 rounded-2xl border bg-card p-3 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="relative min-w-0 flex-1 sm:min-w-[14rem]">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            placeholder={t("site.searchNovels")}
            aria-label={t("site.searchNovels")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-10 pl-9"
          />
        </div>
        {isManual !== true && (genresData?.items.length ?? 0) > 0 && (
          <Select
            value={genreFilter === "all" ? GENRE_FILTER_ALL : String(genreFilter)}
            onValueChange={(v) => {
              if (!v) return
              setGenreFilter(v === GENRE_FILTER_ALL ? "all" : Number(v))
            }}
          >
            <SelectTrigger className="h-10 w-full sm:w-52" aria-label={t("site.colGenre")}>
              <SelectValue>
                {(v: string) => (v === GENRE_FILTER_ALL ? t("site.allGenres") : (genreById.get(Number(v))?.label ?? v))}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={GENRE_FILTER_ALL}>{t("site.allGenres")}</SelectItem>
              {(genresData?.items ?? []).map((g) => (
                <SelectItem key={g.id} value={String(g.id)}>
                  {g.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Select value={status} onValueChange={(v) => v && setStatus(v as LifecycleStatus | "all")}>
          <SelectTrigger className="h-10 w-full sm:w-48" aria-label={t("site.colStatus")}>
            <SelectValue>{(v: string) => statusOptions.find((o) => o.value === v)?.label ?? v}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errorTotal > 0 && (
          <Button
            variant="outline"
            className="h-10"
            onClick={() => retryAllErrorsMutation.mutate()}
            disabled={bulkBusy}
          >
            {retryAllErrorsMutation.isPending ? t("site.queueing") : t("site.retryAllErrors", { count: errorTotal })}
          </Button>
        )}
      </div>

      {/* Thanh hành động hàng loạt */}
      {selectedCount > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-accent px-3 py-2.5 text-sm text-accent-foreground">
          <span className="font-semibold">{t("site.selectedCount", { count: selectedIds.size })}</span>
          <span className="flex-1" />
          {selectedRetryable.length > 0 && (
            <Button
              size="sm"
              onClick={() => bulkRecrawlMutation.mutate(selectedRetryable)}
              disabled={bulkBusy || bulkExportMutation.isPending}
            >
              {bulkRecrawlMutation.isPending ? t("site.sending") : t("site.recrawlSelected", { count: selectedRetryable.length })}
            </Button>
          )}
          {selectedExportable.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => bulkExportMutation.mutate(selectedExportable.map((n) => n.id))}
              disabled={bulkExportMutation.isPending || bulkRecrawlMutation.isPending}
            >
              {bulkExportMutation.isPending ? t("novel.exporting") : t("site.exportSelected", { count: selectedExportable.length })}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
            {t("novel.clearSelection")}
          </Button>
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">{error instanceof ApiError ? error.message : t("app.unknownError")}</p>
      )}

      {novels !== null && total === 0 && !error && (
        <div className="rounded-2xl border border-dashed bg-card">
          <EmptyState
            icon={BookOpen}
            tone="collect"
            title={t("site.emptyNovels")}
            hint={hasFilters ? t("sites.emptyFilteredHint") : t("site.libraryHint")}
            action={
              hasFilters ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    setStatus("all")
                    setGenreFilter("all")
                    setSearch("")
                  }}
                >
                  {t("sites.clearFilters")}
                </Button>
              ) : undefined
            }
          />
        </div>
      )}

      {novels !== null && total > 0 && (
        <>
          <div className="flex items-center justify-between gap-3 text-[13px] text-muted-foreground">
            <label className="flex items-center gap-2">
              <Checkbox
                checked={allSelectableSelected}
                indeterminate={someSelectableSelected}
                disabled={selectableOnPage.length === 0 || bulkBusy}
                onCheckedChange={(checked) => toggleAllOnPage(checked === true)}
                aria-label={t("site.selectAllPage")}
              />
              <span>
                {isManual === true ? t("site.novelsManual") : isManual === false ? t("site.novelsScanned") : t("site.novelsAll")}
              </span>
            </label>
            <span className="font-mono tabular-nums">
              {t("common.range", { from, to, total })}
              {isFetching ? " …" : ""}
            </span>
          </div>

          {view === "grid" ? (
            <ul className="stagger grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
              {novels.map((novel) => {
                const selectable = canSelectNovel(novel)
                const checked = selectedIds.has(novel.id)
                return (
                  <li key={novel.id} className="group relative flex min-w-0 flex-col gap-2">
                    <Link to={`/novels/${novel.id}`} className="block rounded-xl focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none">
                      <BookCover title={novel.title} subtitle={novel.author || novel.source_key} url={novel.cover_url} />
                    </Link>
                    {selectable ? (
                      <div
                        className={cn(
                          "absolute top-2 left-2 rounded-md bg-card/90 p-1 shadow-sm transition-opacity",
                          checked ? "opacity-100" : "opacity-100 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100",
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          disabled={bulkBusy}
                          onCheckedChange={(v) => toggleOne(novel.id, v === true)}
                          aria-label={t("site.selectNovel", { stt: offset + novels.indexOf(novel) + 1 })}
                        />
                      </div>
                    ) : null}
                    <div className="min-w-0 space-y-1.5">
                      <Link to={`/novels/${novel.id}`} className="line-clamp-2 text-sm leading-snug font-semibold hover:underline" title={novel.title}>
                        {novel.title}
                      </Link>
                      <div className="flex items-center justify-between gap-1">
                        <StatusBadge status={novel.lifecycle_status} />
                        {rowActions(novel, true)}
                      </div>
                      <NovelProgress novel={novel} />
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            <>
              {/* Mobile: danh sách thẻ */}
              <ul className="space-y-2 md:hidden">
                {novels.map((novel, index) => {
                  const selectable = canSelectNovel(novel)
                  const checked = selectedIds.has(novel.id)
                  return (
                    <li key={novel.id} className={cn("rounded-2xl border bg-card p-3.5", checked && "border-primary/40 bg-accent/40")}>
                      <div className="flex items-start gap-3">
                        <Checkbox
                          className="mt-1"
                          checked={checked}
                          disabled={!selectable || bulkBusy}
                          onCheckedChange={(v) => toggleOne(novel.id, v === true)}
                          aria-label={t("site.selectNovel", { stt: offset + index + 1 })}
                        />
                        <div className="min-w-0 flex-1 space-y-2">
                          <Link to={`/novels/${novel.id}`} className="block font-semibold leading-snug hover:underline">
                            {novel.title}
                          </Link>
                          <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground">
                            <StatusBadge status={novel.lifecycle_status} />
                            {isManual !== true ? <span className="truncate">{genreLabel(novel)}</span> : null}
                          </div>
                          <NovelProgress novel={novel} />
                          {novel.error_message ? (
                            <p className="line-clamp-2 text-[13px] text-danger">{novel.error_message}</p>
                          ) : null}
                        </div>
                      </div>
                      <div className="mt-2 flex justify-end">{rowActions(novel)}</div>
                    </li>
                  )
                })}
              </ul>
              {/* Desktop: bảng */}
              <div className="hidden overflow-hidden rounded-2xl border bg-card md:block">
                <table className="w-full text-sm">
                  <thead className="bg-muted/60 text-left text-xs font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                    <tr>
                      <th className="w-10 px-3 py-3">
                        <span className="sr-only">{t("site.selectAllPage")}</span>
                      </th>
                      <th className="w-12 px-1 py-3 text-center">#</th>
                      <th className="w-[40%] px-3 py-3">{t("site.colTitle")}</th>
                      {isManual !== true && <th className="px-3 py-3">{t("site.colGenre")}</th>}
                      <th className="px-3 py-3">{t("site.colStatus")}</th>
                      <th className="w-40 px-3 py-3">{t("site.colProgress")}</th>
                      <th className="px-3 py-3 text-right">{t("site.colActions")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {novels.map((novel, index) => {
                      const selectable = canSelectNovel(novel)
                      const checked = selectedIds.has(novel.id)
                      const stt = offset + index + 1
                      return (
                        <tr key={novel.id} className={cn("transition-colors hover:bg-muted/40", checked && "bg-accent/40")}>
                          <td className="px-3 py-3">
                            <Checkbox
                              checked={checked}
                              disabled={!selectable || bulkBusy}
                              onCheckedChange={(v) => toggleOne(novel.id, v === true)}
                              aria-label={t("site.selectNovel", { stt })}
                            />
                          </td>
                          <td className="px-1 py-3 text-center font-mono text-xs text-muted-foreground tabular-nums">{stt}</td>
                          <td className="max-w-0 px-3 py-3">
                            <Link to={`/novels/${novel.id}`} className="block truncate font-semibold hover:underline" title={novel.title}>
                              {novel.title}
                            </Link>
                            {novel.error_message && (
                              <p className="truncate text-[13px] text-danger" title={novel.error_message}>
                                {novel.error_message}
                              </p>
                            )}
                          </td>
                          {isManual !== true && (
                            <td className="px-3 py-3 text-[13px] text-muted-foreground">{genreLabel(novel)}</td>
                          )}
                          <td className="px-3 py-3">
                            <StatusBadge status={novel.lifecycle_status} />
                          </td>
                          <td className="px-3 py-3">
                            <NovelProgress novel={novel} />
                          </td>
                          <td className="px-3 py-3 text-right">{rowActions(novel)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} disabled={offset === 0}>
                {t("common.prevArrow")}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setOffset((o) => o + PAGE_SIZE)} disabled={offset + PAGE_SIZE >= total}>
                {t("common.nextArrow")}
              </Button>
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmDeleteId != null}
        onOpenChange={(open) => !open && setConfirmDeleteId(null)}
        title={t("common.deleteTitle")}
        description={t("site.deleteConfirm")}
        confirmLabel={t("site.delete")}
        confirming={deleteNovelMutation.isPending}
        onConfirm={() => {
          if (confirmDeleteId != null) deleteNovelMutation.mutate(confirmDeleteId)
        }}
      />
    </div>
  )
}

function NovelProgress({ novel }: { novel: Novel }) {
  const t = useT()
  const done = novel.crawled_chapters ?? novel.last_chapter_index
  const totalCh = novel.total_chapters
  if (!(done > 0 || totalCh)) return <span className="text-[13px] text-muted-foreground">—</span>
  const pct = totalCh ? (done / totalCh) * 100 : null
  const live = novel.lifecycle_status === "crawling"
  return (
    <div className="space-y-1">
      <Progress value={pct} tone={novel.lifecycle_status === "error" ? "danger" : "collect"} live={live} size="sm" />
      <p className="font-mono text-xs text-muted-foreground tabular-nums">
        {done}/{totalCh ?? "?"}
        {novel.failed_chapters ? (
          <span className="ml-1 text-danger">
            · {novel.failed_chapters} {t("novel.failedShort")}
          </span>
        ) : null}
      </p>
    </div>
  )
}

function NovelActions({
  novel,
  compact,
  busy,
  locked,
  deletePending,
  onRetry,
  onForce,
  onDelete,
}: {
  novel: Novel
  compact: boolean
  busy: boolean
  locked: boolean
  deletePending: boolean
  onRetry: () => void
  onForce: () => void
  onDelete: () => void
}) {
  const t = useT()
  const s = novel.lifecycle_status
  if (s === "crawling") {
    return <span className="text-[13px] text-muted-foreground">{t("site.crawling")}</span>
  }
  return (
    <div className="inline-flex items-center justify-end gap-1">
      {!compact && s === "error" && (
        <Button size="sm" variant="outline" onClick={onRetry} disabled={busy || locked}>
          {busy ? t("site.retrying") : t("site.retry")}
        </Button>
      )}
      {!compact && s === "fully_crawled" && (
        <Link to={`/novels/${novel.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
          {t("site.openNovel")}
        </Link>
      )}
      {!compact && s === "rejected" && (
        <Button size="sm" variant="outline" onClick={onForce} disabled={busy || locked}>
          {busy ? t("site.processing") : t("site.forceAccept")}
        </Button>
      )}
      <ActionMenu
        label={<><MoreHorizontal className="size-4" aria-hidden /><span className="sr-only">{t("novel.moreActions")}</span></>}
        size="sm"
        variant="ghost"
        align="end"
        showChevron={false}
        disabled={deletePending || busy || locked}
      >
        {compact && s === "error" ? (
          <ActionMenuItem disabled={busy} onSelect={onRetry}>
            {t("site.retry")}
          </ActionMenuItem>
        ) : null}
        {compact && s === "rejected" ? (
          <ActionMenuItem disabled={busy} onSelect={onForce}>
            {t("site.forceAccept")}
          </ActionMenuItem>
        ) : null}
        {s === "fully_crawled" ? (
          <ActionMenuItem disabled={busy} onSelect={onRetry}>
            {busy ? t("site.syncing") : t("site.sync")}
          </ActionMenuItem>
        ) : null}
        <ActionMenuItem destructive disabled={deletePending || busy} onSelect={onDelete}>
          {t("site.delete")}
        </ActionMenuItem>
      </ActionMenu>
    </div>
  )
}
