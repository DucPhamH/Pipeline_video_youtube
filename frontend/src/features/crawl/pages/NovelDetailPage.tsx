import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMemo, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useT } from "@/i18n"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { PageHeader, PageShell, StatChip } from "@/components/PageChrome"
import { queryKeys } from "@/lib/query-client"
import { ApiError } from "../../../api/client"
import type { Chapter } from "../../../api/types"
import { crawlApi } from "../api"
import { ChapterReviewDialog } from "../components/ChapterReviewDialog"
import { StatusBadge } from "../components/StatusBadge"

const POLL_MS = 3000
const PAGE_SIZE = 20

const STATUS_VALUES = ["all", "pending", "crawled", "failed"] as const
const REVIEW_VALUES = ["all", "reviewed", "unreviewed"] as const
const CLEANED_VALUES = ["all", "cleaned", "raw"] as const
const CHAPTER_PRESETS = ["all", "need_smooth", "need_review", "failed"] as const
type ChapterPreset = (typeof CHAPTER_PRESETS)[number]

function canSmoothChapter(ch: Chapter): boolean {
  return ch.status === "crawled"
}

function detectChapterPreset(
  status: (typeof STATUS_VALUES)[number],
  review: (typeof REVIEW_VALUES)[number],
  cleaned: (typeof CLEANED_VALUES)[number],
): ChapterPreset | null {
  if (status === "all" && review === "all" && cleaned === "all") return "all"
  if (status === "crawled" && review === "all" && cleaned === "raw") return "need_smooth"
  if (status === "crawled" && review === "unreviewed" && cleaned === "cleaned") return "need_review"
  if (status === "failed" && review === "all" && cleaned === "all") return "failed"
  return null
}

export function NovelDetailPage() {
  const { id } = useParams<{ id: string }>()
  const novelId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const t = useT()
  const [reviewingChapter, setReviewingChapter] = useState<{ id: number; title: string } | null>(null)
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_VALUES)[number]>("all")
  const [reviewFilter, setReviewFilter] = useState<(typeof REVIEW_VALUES)[number]>("all")
  const [cleanedFilter, setCleanedFilter] = useState<(typeof CLEANED_VALUES)[number]>("all")
  const [search, setSearch] = useState("")
  const [offset, setOffset] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())
  const [lastSmoothSummary, setLastSmoothSummary] = useState<string | null>(null)
  const [confirmDeleteNovel, setConfirmDeleteNovel] = useState(false)
  const [confirmDeleteChapterId, setConfirmDeleteChapterId] = useState<number | null>(null)
  const debouncedSearch = useDebouncedValue(search.trim(), 350)

  const statusOptions = useMemo(
    () =>
      [
        { value: "all", label: t("novel.statusAll") },
        { value: "pending", label: t("novel.statusPending") },
        { value: "crawled", label: t("novel.statusCrawled") },
        { value: "failed", label: t("novel.statusError") },
      ] as const,
    [t],
  )

  const reviewOptions = useMemo(
    () =>
      [
        { value: "all", label: t("novel.reviewAll") },
        { value: "reviewed", label: t("novel.reviewDone") },
        { value: "unreviewed", label: t("novel.reviewPending") },
      ] as const,
    [t],
  )

  const cleanedOptions = useMemo(
    () =>
      [
        { value: "all", label: t("novel.cleanedAll") },
        { value: "cleaned", label: t("novel.cleanedYes") },
        { value: "raw", label: t("novel.cleanedNo") },
      ] as const,
    [t],
  )

  const effectiveStatus = statusFilter === "all" ? undefined : statusFilter
  const effectiveReviewed =
    reviewFilter === "all" ? undefined : reviewFilter === "reviewed"
  const effectiveCleaned =
    cleanedFilter === "all" ? undefined : cleanedFilter === "cleaned"

  // Đổi truyện/bộ lọc → reset trang + selection NGAY TRONG RENDER (không
  // qua useEffect) — sửa 17/9/2026: bản cũ dùng effect để setOffset(0), nên
  // đổi filter lúc offset > 0 khiến query chạy 1 lần với offset CŨ (còn
  // hiệu lực ở chính render đó) rồi mới render lại với offset=0 → tốn 1
  // request thật sự thừa mỗi lần đổi filter, oxlint gắn cờ
  // `react(set-state-in-effect)` đúng chỗ này. Đồng thời fix thêm 1 bug tồn
  // tại từ trước: đổi filter KHÔNG kèm effect reset `novelId` — chuyển giữa
  // 2 trang chi tiết truyện trong khi đang ở trang 3+ sẽ giữ nguyên offset
  // cũ (có thể vượt quá số chương của truyện MỚI), giờ gộp chung 1 khoá.
  const resetKey = `${novelId}|${effectiveStatus}|${effectiveReviewed}|${cleanedFilter}|${debouncedSearch}`
  const [prevResetKey, setPrevResetKey] = useState(resetKey)
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey)
    setOffset(0)
    setSelectedIds(new Set())
  }

  const chapterParams = {
    status: effectiveStatus,
    search: debouncedSearch || undefined,
    reviewed: effectiveReviewed,
    has_cleaned: effectiveCleaned,
    limit: PAGE_SIZE,
    offset,
  }

  const { data: novel, error, isLoading } = useQuery({
    queryKey: queryKeys.novel(novelId),
    queryFn: () => crawlApi.getNovel(novelId),
    enabled: Number.isFinite(novelId),
    refetchInterval: (q) => (q.state.data?.lifecycle_status === "crawling" ? POLL_MS : false),
  })

  const {
    data: chaptersData,
    error: chaptersError,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: queryKeys.chapters(novelId, chapterParams),
    queryFn: () => crawlApi.listChapters(novelId, chapterParams),
    enabled: Number.isFinite(novelId),
    placeholderData: (prev) => prev,
    refetchInterval: () => (novel?.lifecycle_status === "crawling" ? POLL_MS : false),
  })

  const { data: exportStatus, refetch: refetchExportStatus } = useQuery({
    queryKey: ["export-status", novelId],
    queryFn: () => crawlApi.getExportStatus(novelId),
    enabled: Number.isFinite(novelId),
  })

  const { data: failedCountData } = useQuery({
    queryKey: ["chapters-failed-count", novelId],
    queryFn: () => crawlApi.listChapters(novelId, { status: "failed", limit: 1, offset: 0 }),
    enabled: Number.isFinite(novelId),
  })
  const failedChapterTotal = failedCountData?.total ?? 0

  const chapters = chaptersData?.items ?? []
  const total = chaptersData?.total ?? 0
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)

  const smoothableOnPage = useMemo(() => chapters.filter(canSmoothChapter), [chapters])
  const allSmoothableSelected =
    smoothableOnPage.length > 0 && smoothableOnPage.every((c) => selectedIds.has(c.id))
  const someSmoothableSelected =
    smoothableOnPage.some((c) => selectedIds.has(c.id)) && !allSmoothableSelected
  const selectedCount = selectedIds.size

  const canSmoothNovel =
    novel?.lifecycle_status === "fully_crawled" ||
    novel?.lifecycle_status === "error" ||
    novel?.lifecycle_status === "translating" ||
    novel?.lifecycle_status === "ready_for_video"

  const canSendToTranslate =
    novel?.lifecycle_status === "fully_crawled" ||
    novel?.lifecycle_status === "error" ||
    novel?.lifecycle_status === "ready_for_video" ||
    novel?.lifecycle_status === "translating"

  const activePreset = detectChapterPreset(statusFilter, reviewFilter, cleanedFilter)

  const pipelineStep = useMemo(() => {
    if (!exportStatus || exportStatus.crawled <= 0) return null
    if (exportStatus.cleaned < exportStatus.crawled) return "smooth" as const
    if (exportStatus.reviewed < exportStatus.cleaned) return "review" as const
    if (exportStatus.can_export_workbook || exportStatus.can_export_bundle) return "export" as const
    return null
  }, [exportStatus])

  const [selectingAll, setSelectingAll] = useState(false)

  function applyChapterPreset(preset: ChapterPreset) {
    setOffset(0)
    setSelectedIds(new Set())
    if (preset === "all") {
      setStatusFilter("all")
      setReviewFilter("all")
      setCleanedFilter("all")
    } else if (preset === "need_smooth") {
      setStatusFilter("crawled")
      setReviewFilter("all")
      setCleanedFilter("raw")
    } else if (preset === "need_review") {
      setStatusFilter("crawled")
      setReviewFilter("unreviewed")
      setCleanedFilter("cleaned")
    } else {
      setStatusFilter("failed")
      setReviewFilter("all")
      setCleanedFilter("all")
    }
  }

  async function openFirstUnreviewed() {
    try {
      const page = await crawlApi.listChapters(novelId, {
        status: "crawled",
        reviewed: false,
        has_cleaned: true,
        limit: 50,
        offset: 0,
      })
      const ch = page.items[0]
      if (!ch) {
        toast.message(t("novel.reviewAllNone"))
        return
      }
      setReviewingChapter({ id: ch.id, title: ch.title })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function goNextReview() {
    if (!reviewingChapter) return
    const items = chaptersData?.items ?? []
    const idx = items.findIndex((c) => c.id === reviewingChapter.id)
    const nextOnPage = items
      .slice(idx + 1)
      .find((c) => c.status === "crawled" && !c.reviewed && c.has_cleaned)
    if (nextOnPage) {
      setReviewingChapter({ id: nextOnPage.id, title: nextOnPage.title })
      return
    }
    try {
      const page = await crawlApi.listChapters(novelId, {
        status: "crawled",
        reviewed: false,
        has_cleaned: true,
        limit: 30,
        offset: 0,
      })
      const next = page.items.find((c) => c.id !== reviewingChapter.id)
      if (next) {
        setReviewingChapter({ id: next.id, title: next.title })
      } else {
        setReviewingChapter(null)
        toast.message(t("review.noMore"))
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  const hasReviewNext = useMemo(() => {
    if (!reviewingChapter) return false
    const items = chaptersData?.items ?? []
    const idx = items.findIndex((c) => c.id === reviewingChapter.id)
    if (
      idx >= 0 &&
      items.slice(idx + 1).some((c) => c.status === "crawled" && !c.reviewed && c.has_cleaned)
    ) {
      return true
    }
    // Optimistic: allow next; goNextReview will close if none left.
    return true
  }, [reviewingChapter, chaptersData?.items])

  async function selectAllCrawledChapters() {
    setSelectingAll(true)
    try {
      const ids: number[] = []
      let off = 0
      const limit = 100
      for (;;) {
        const page = await crawlApi.listChapters(novelId, {
          status: "crawled",
          limit,
          offset: off,
        })
        for (const ch of page.items) ids.push(ch.id)
        if (off + limit >= page.total || page.items.length === 0) break
        off += limit
      }
      setSelectedIds(new Set(ids))
      toast.message(
        ids.length ? t("novel.selectedCrawled", { count: ids.length }) : t("novel.noCrawled"),
      )
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSelectingAll(false)
    }
  }

  const smoothMutation = useMutation({
    mutationFn: (chapterIds?: number[]) => crawlApi.smoothNovel(novelId, chapterIds),
    onSuccess: (result, chapterIds) => {
      const scope = chapterIds?.length
        ? t("novel.smoothScopeSelected", { count: result.chapters_smoothed })
        : t("novel.smoothScopeAll")
      const summary =
        t("novel.smoothSummary", { count: result.chapters_smoothed, scope }) +
        (result.removed_lines ? t("novel.smoothRemoved", { count: result.removed_lines }) : "")
      setLastSmoothSummary(summary)
      setSelectedIds(new Set())
      setStatusFilter("crawled")
      setReviewFilter("unreviewed")
      setCleanedFilter("cleaned")
      toast.success(summary, {
        description: t("novel.reviewHint"),
        action:
          result.chapter_ids.length > 0
            ? {
                label: t("novel.reviewFirst"),
                onClick: () => {
                  const firstId = result.chapter_ids[0]
                  const ch = chapters.find((c) => c.id === firstId)
                  setReviewingChapter({
                    id: firstId,
                    title: ch?.title ?? t("novel.chapterFallback", { id: firstId }),
                  })
                },
              }
            : undefined,
      })
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      void refetch()
      void refetchExportStatus()
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const sendToTranslateMutation = useMutation({
    mutationFn: (requireCleaned: boolean) =>
      crawlApi.sendToTranslate(novelId, { require_cleaned: requireCleaned, start_job: false }),
    onSuccess: (result) => {
      toast.success(t("novel.sendToTranslateOk"), {
        description:
          result.unreviewed > 0
            ? t("novel.sendToTranslateUnreviewed", { count: result.unreviewed })
            : undefined,
        action: {
          label: t("novel.openTranslate"),
          onClick: () => navigate(result.translate_path || `/translate/${result.work_id}`),
        },
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
      navigate(result.translate_path || `/translate/${result.work_id}`)
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const retryChapterMutation = useMutation({
    mutationFn: (chapterId: number) => crawlApi.retryChapter(chapterId),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(
          result.novel_completed ? t("novel.retryOkNovel") : t("novel.retryOkChapter"),
        )
      } else {
        toast.error(result.error ?? t("novel.retryFail"))
      }
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      // novel_completed = ghi chú "Thiếu N chương" (mục 9.2b) vừa được xoá
      // + lifecycle_status có thể vừa đổi -> cần load lại chính Novel.
      if (result.novel_completed) void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
      void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["chapters-failed-count", novelId] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const retryNovelMutation = useMutation({
    mutationFn: () => crawlApi.retryNovel(novelId),
    onSuccess: () => {
      toast.message(t("novel.retryNovelQueued"))
      void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["chapters-failed-count", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const deleteNovelMutation = useMutation({
    mutationFn: () => crawlApi.deleteNovel(novelId),
    onSuccess: () => {
      setConfirmDeleteNovel(false)
      toast.success(t("novel.deleteNovelOk"))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
      if (novel?.source_key) navigate(`/sites/${novel.source_key}`)
      else navigate("/sites")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const deleteChapterMutation = useMutation({
    mutationFn: (chapterId: number) => crawlApi.deleteChapter(chapterId),
    onSuccess: () => {
      setConfirmDeleteChapterId(null)
      toast.success(t("novel.deleteChapterOk"))
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
      void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const exportWorkbookMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelWorkbook(novelId),
    onSuccess: () => toast.success(t("novel.exportOk")),
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const exportTxtMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelTxt(novelId),
    onSuccess: () => toast.success(t("novel.exportTxtOk")),
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const exportEpubMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelEpub(novelId),
    onSuccess: () => toast.success(t("novel.exportEpubOk")),
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const exportBundleMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelBundle(novelId),
    onSuccess: () => toast.success(t("novel.exportBundleOk")),
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const exportBusy =
    exportWorkbookMutation.isPending ||
    exportTxtMutation.isPending ||
    exportEpubMutation.isPending ||
    exportBundleMutation.isPending

  const reviewAllMutation = useMutation({
    mutationFn: () => crawlApi.reviewAllChapters(novelId),
    onSuccess: (result) => {
      if (result.chapters_reviewed > 0) {
        toast.success(t("novel.reviewAllOk", { count: result.chapters_reviewed }))
      } else {
        toast.message(t("novel.reviewAllNone"))
      }
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

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
      for (const c of smoothableOnPage) {
        if (checked) next.add(c.id)
        else next.delete(c.id)
      }
      return next
    })
  }

  if (!Number.isFinite(novelId)) {
    return (
      <PageShell>
        <PageHeader title={t("app.unknownError")} description={t("novel.invalidId")} />
        <p className="text-sm text-muted-foreground">
          <Link to="/sites" className="text-primary hover:underline">
            {t("common.backSites")}
          </Link>
        </p>
      </PageShell>
    )
  }

  if (error) {
    return (
      <PageShell>
        <PageHeader title={t("app.unknownError")} />
        <p className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : t("app.unknownError")}
        </p>
      </PageShell>
    )
  }
  if (isLoading || !novel) {
    return (
      <PageShell>
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow={
          <Link
            to={`/sites/${novel.source_key}`}
            className="hover:text-foreground hover:underline"
          >
            ← {novel.source_key}
          </Link>
        }
        title={novel.title}
        description={
          <>
            {novel.author ? `${novel.author} · ` : null}
            {t("novel.progress", {
              last: novel.last_chapter_index,
              total: novel.total_chapters ?? "?",
            })}
            {novel.is_manual && t("novel.manual")}
          </>
        }
        actions={
          <>
            <StatusBadge status={novel.lifecycle_status} />
            {canSendToTranslate && (
              <ActionMenu
                label={
                  sendToTranslateMutation.isPending
                    ? t("novel.sendingToTranslate")
                    : t("novel.sendToTranslate")
                }
                variant="default"
                disabled={sendToTranslateMutation.isPending}
              >
                <ActionMenuItem
                  disabled={sendToTranslateMutation.isPending}
                  onSelect={() => sendToTranslateMutation.mutate(true)}
                >
                  {t("novel.sendToTranslateCleaned")}
                </ActionMenuItem>
                <ActionMenuItem
                  disabled={sendToTranslateMutation.isPending}
                  onSelect={() => sendToTranslateMutation.mutate(false)}
                >
                  {t("novel.sendToTranslateForce")}
                </ActionMenuItem>
              </ActionMenu>
            )}
            {canSmoothNovel && (
              <ActionMenu label={t("novel.prepare")} variant="secondary" disabled={smoothMutation.isPending || reviewAllMutation.isPending}>
                <ActionMenuItem
                  disabled={smoothMutation.isPending}
                  onSelect={() => smoothMutation.mutate(undefined)}
                >
                  {smoothMutation.isPending ? t("novel.smoothing") : t("novel.smoothAll")}
                </ActionMenuItem>
                <ActionMenuItem
                  disabled={reviewAllMutation.isPending || (exportStatus?.cleaned ?? 0) === 0}
                  onSelect={() => reviewAllMutation.mutate()}
                >
                  {reviewAllMutation.isPending ? t("novel.reviewingAll") : t("novel.reviewAllAction")}
                </ActionMenuItem>
              </ActionMenu>
            )}
            {exportStatus?.can_export_workbook && (
              <ActionMenu
                label={exportBusy ? t("novel.exporting") : t("novel.export")}
                variant="default"
                disabled={exportBusy}
              >
                <ActionMenuItem
                  disabled={exportBusy}
                  onSelect={() => exportBundleMutation.mutate()}
                >
                  {t("novel.exportBundle")}
                </ActionMenuItem>
                <ActionMenuItem
                  disabled={exportBusy}
                  onSelect={() => exportWorkbookMutation.mutate()}
                >
                  {t("novel.exportWorkbook")}
                </ActionMenuItem>
                <ActionMenuItem
                  disabled={exportBusy}
                  onSelect={() => exportTxtMutation.mutate()}
                >
                  {t("novel.exportTxt")}
                </ActionMenuItem>
                <ActionMenuItem
                  disabled={exportBusy}
                  onSelect={() => exportEpubMutation.mutate()}
                >
                  {t("novel.exportEpub")}
                </ActionMenuItem>
              </ActionMenu>
            )}
            {novel.lifecycle_status !== "crawling" && (
              <ActionMenu label={t("novel.moreActions")} variant="outline">
                {(novel.lifecycle_status === "error" || novel.lifecycle_status === "fully_crawled") && (
                  <ActionMenuItem
                    disabled={retryNovelMutation.isPending}
                    onSelect={() => retryNovelMutation.mutate()}
                  >
                    {retryNovelMutation.isPending ? t("novel.retryingNovel") : t("novel.retryNovel")}
                  </ActionMenuItem>
                )}
                <ActionMenuItem
                  destructive
                  disabled={deleteNovelMutation.isPending}
                  onSelect={() => setConfirmDeleteNovel(true)}
                >
                  {t("novel.deleteNovel")}
                </ActionMenuItem>
              </ActionMenu>
            )}
          </>
        }
      />

      {exportStatus && exportStatus.crawled > 0 && (
        <div className="grid gap-2 sm:grid-cols-3">
          <StatChip label={t("novel.statCrawled")} value={exportStatus.crawled} />
          <StatChip
            label={t("novel.statCleaned")}
            value={exportStatus.cleaned}
            tone={exportStatus.cleaned > 0 ? "success" : "default"}
          />
          <StatChip
            label={t("novel.statReviewed")}
            value={exportStatus.reviewed}
            tone={exportStatus.reviewed > 0 ? "success" : "warn"}
          />
        </div>
      )}

      {pipelineStep === "smooth" && canSmoothNovel && (
        <Card className="border-sky-500/20 bg-sky-500/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="min-w-0">
              <p className="text-sm font-medium">{t("novel.pipelineSmoothTitle")}</p>
              <p className="text-xs text-muted-foreground">
                {t("novel.pipelineSmoothDesc", {
                  cleaned: exportStatus?.cleaned ?? 0,
                  crawled: exportStatus?.crawled ?? 0,
                })}
              </p>
            </div>
            <Button
              size="sm"
              disabled={smoothMutation.isPending}
              onClick={() => smoothMutation.mutate(undefined)}
            >
              {smoothMutation.isPending ? t("novel.smoothing") : t("novel.pipelineSmoothAction")}
            </Button>
          </CardContent>
        </Card>
      )}
      {pipelineStep === "review" && (
        <Card className="border-amber-500/20 bg-amber-500/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="min-w-0">
              <p className="text-sm font-medium">{t("novel.pipelineReviewTitle")}</p>
              <p className="text-xs text-muted-foreground">
                {t("novel.pipelineReviewDesc", {
                  reviewed: exportStatus?.reviewed ?? 0,
                  cleaned: exportStatus?.cleaned ?? 0,
                })}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => void openFirstUnreviewed()}>
                {t("novel.pipelineReviewAction")}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={reviewAllMutation.isPending}
                onClick={() => reviewAllMutation.mutate()}
              >
                {reviewAllMutation.isPending ? t("novel.reviewingAll") : t("novel.reviewAllAction")}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
      {pipelineStep === "export" && exportStatus?.can_export_workbook && (
        <Card className="border-emerald-500/20 bg-emerald-500/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="min-w-0">
              <p className="text-sm font-medium">{t("novel.pipelineExportTitle")}</p>
              <p className="text-xs text-muted-foreground">{t("novel.pipelineExportDesc")}</p>
            </div>
            <Button
              size="sm"
              disabled={exportBusy}
              onClick={() => exportBundleMutation.mutate()}
            >
              {exportBundleMutation.isPending ? t("novel.exporting") : t("novel.pipelineExportAction")}
            </Button>
          </CardContent>
        </Card>
      )}

      {(novel.error_message || novel.lifecycle_status === "error" || failedChapterTotal > 0) && (
        <Alert>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-destructive">
              {novel.error_message ||
                (failedChapterTotal > 0
                  ? t("novel.failedChaptersHint", { count: failedChapterTotal })
                  : t("lifecycle.error"))}
            </span>
            <div className="flex flex-wrap gap-2">
              {failedChapterTotal > 0 && (
                <Button size="sm" variant="outline" onClick={() => applyChapterPreset("failed")}>
                  {t("novel.presetFailed")}
                </Button>
              )}
              {(novel.lifecycle_status === "error" || novel.lifecycle_status === "fully_crawled") && (
                <Button
                  size="sm"
                  disabled={retryNovelMutation.isPending}
                  onClick={() => retryNovelMutation.mutate()}
                >
                  {retryNovelMutation.isPending ? t("novel.retryingNovel") : t("novel.retryNovel")}
                </Button>
              )}
            </div>
          </AlertDescription>
        </Alert>
      )}

      {canSmoothNovel && (
        <Card>
          <CardContent className="space-y-3 pt-1">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium">{t("novel.smoothTitle")}</p>
                <p className="text-xs text-muted-foreground">{t("novel.smoothHint")}</p>
              </div>
              <Button
                size="sm"
                disabled={smoothMutation.isPending}
                onClick={() => smoothMutation.mutate(undefined)}
                title={t("novel.smoothAllTitle")}
              >
                {smoothMutation.isPending && selectedCount === 0
                  ? t("novel.smoothing")
                  : t("novel.smoothAll")}
              </Button>
            </div>
            {selectedCount > 0 && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2.5 text-sm">
                <span className="font-medium text-foreground">
                  {t("novel.selectedCount", { count: selectedCount })}
                </span>
                <Button
                  size="sm"
                  disabled={smoothMutation.isPending}
                  onClick={() => smoothMutation.mutate(Array.from(selectedIds))}
                >
                  {smoothMutation.isPending ? t("novel.smoothing") : t("novel.smoothSelected")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={selectingAll || smoothMutation.isPending}
                  onClick={() => void selectAllCrawledChapters()}
                >
                  {selectingAll ? t("novel.selecting") : t("novel.selectAllPages")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={smoothMutation.isPending}
                  onClick={() => setSelectedIds(new Set())}
                >
                  {t("novel.clearSelection")}
                </Button>
              </div>
            )}
            {lastSmoothSummary && (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-sm">
                <p>{lastSmoothSummary}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {CHAPTER_PRESETS.map((preset) => (
          <Button
            key={preset}
            type="button"
            size="sm"
            variant={activePreset === preset ? "default" : "outline"}
            onClick={() => applyChapterPreset(preset)}
          >
            {preset === "all"
              ? t("novel.presetAll")
              : preset === "need_smooth"
                ? t("novel.presetNeedSmooth")
                : preset === "need_review"
                  ? t("novel.presetNeedReview")
                  : t("novel.presetFailed")}
            {preset === "failed" && failedChapterTotal > 0 ? ` (${failedChapterTotal})` : ""}
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl bg-muted/40 p-3 ring-1 ring-border">
        <Select
          value={statusFilter}
          onValueChange={(v) => v && setStatusFilter(v as typeof statusFilter)}
        >
          <SelectTrigger className="h-9 w-44 bg-background">
            <SelectValue>
              {(v: string) => statusOptions.find((o) => o.value === v)?.label ?? v}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={reviewFilter}
          onValueChange={(v) => v && setReviewFilter(v as typeof reviewFilter)}
        >
          <SelectTrigger className="h-9 w-44 bg-background">
            <SelectValue>
              {(v: string) => reviewOptions.find((o) => o.value === v)?.label ?? v}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {reviewOptions.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={cleanedFilter}
          onValueChange={(v) => v && setCleanedFilter(v as typeof cleanedFilter)}
        >
          <SelectTrigger className="h-9 w-44 bg-background">
            <SelectValue>
              {(v: string) => cleanedOptions.find((o) => o.value === v)?.label ?? v}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {cleanedOptions.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="search"
          placeholder={t("novel.searchChapters")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 min-w-[12rem] flex-1 bg-background sm:max-w-xs"
        />
        {total > 0 && (
          <span className="ml-auto text-xs text-muted-foreground">
            {t("common.range", { from, to, total })}
            {isFetching ? "…" : ""}
          </span>
        )}
      </div>

      {chaptersError && (
        <p className="text-sm text-destructive">
          {chaptersError instanceof ApiError ? chaptersError.message : t("app.unknownError")}
        </p>
      )}

      <Card className="overflow-hidden py-0">
        <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10 px-2">
                <Checkbox
                  checked={allSmoothableSelected}
                  indeterminate={someSmoothableSelected}
                  disabled={!canSmoothNovel || smoothableOnPage.length === 0 || smoothMutation.isPending}
                  onCheckedChange={(checked) => toggleAllOnPage(checked === true)}
                  aria-label={t("novel.selectAllPage")}
                />
              </TableHead>
              <TableHead className="w-12">#</TableHead>
              <TableHead>{t("novel.colTitle")}</TableHead>
              <TableHead>{t("novel.colStatus")}</TableHead>
              <TableHead>{t("novel.colSmooth")}</TableHead>
              <TableHead>{t("novel.colReview")}</TableHead>
              <TableHead>{t("novel.colError")}</TableHead>
              <TableHead className="text-right">{t("novel.colActions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {chapters.map((ch) => {
              const smoothable = canSmoothChapter(ch)
              return (
                <TableRow key={ch.id} data-state={selectedIds.has(ch.id) ? "selected" : undefined}>
                  <TableCell className="px-2">
                    <Checkbox
                      checked={selectedIds.has(ch.id)}
                      disabled={!canSmoothNovel || !smoothable || smoothMutation.isPending}
                      onCheckedChange={(v) => toggleOne(ch.id, v === true)}
                      aria-label={t("novel.selectChapter", { index: ch.chapter_index })}
                    />
                  </TableCell>
                  <TableCell className="text-muted-foreground">{ch.chapter_index}</TableCell>
                  <TableCell className="font-medium">{ch.title}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {ch.status === "pending"
                        ? t("novel.statusPending")
                        : ch.status === "crawled"
                          ? t("novel.statusCrawled")
                          : ch.status === "failed"
                            ? t("novel.statusError")
                            : ch.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {ch.has_cleaned ? (
                      <Badge className="bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200">
                        {t("novel.badgeCleaned")}
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-muted-foreground">
                        {t("novel.badgeDash")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {ch.reviewed ? (
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300">
                        {t("novel.badgeReviewed")}
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-muted-foreground">
                        {t("novel.badgeUnreviewed")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-destructive">{ch.error_message ?? ""}</TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <div className="inline-flex items-center justify-end gap-1">
                      {ch.status === "crawled" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setReviewingChapter({ id: ch.id, title: ch.title })}
                        >
                          {t("novel.btnReview")}
                        </Button>
                      )}
                      {(ch.status === "failed" || ch.status === "unsupported") && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={retryChapterMutation.isPending && retryChapterMutation.variables === ch.id}
                          onClick={() => retryChapterMutation.mutate(ch.id)}
                        >
                          {retryChapterMutation.isPending && retryChapterMutation.variables === ch.id
                            ? t("novel.crawling")
                            : t("novel.btnRetry")}
                        </Button>
                      )}
                      {(smoothable && canSmoothNovel) || novel.lifecycle_status !== "crawling" ? (
                        <ActionMenu label="⋯" size="sm" variant="ghost" align="end" showChevron={false}>
                          {smoothable && canSmoothNovel ? (
                            <ActionMenuItem
                              disabled={smoothMutation.isPending}
                              onSelect={() => smoothMutation.mutate([ch.id])}
                            >
                              {t("novel.btnSmooth")}
                            </ActionMenuItem>
                          ) : null}
                          {novel.lifecycle_status !== "crawling" ? (
                            <ActionMenuItem
                              destructive
                              disabled={
                                deleteChapterMutation.isPending &&
                                deleteChapterMutation.variables === ch.id
                              }
                              onSelect={() => setConfirmDeleteChapterId(ch.id)}
                            >
                              {t("novel.deleteChapter")}
                            </ActionMenuItem>
                          ) : null}
                        </ActionMenu>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
            {chapters.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="py-6 text-center text-sm text-muted-foreground">
                  {novel.lifecycle_status === "crawling" && statusFilter === "all" && !debouncedSearch
                    ? t("novel.emptyCrawling")
                    : t("novel.emptyFilter")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </div>
      </Card>

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

      {reviewingChapter && (
        <ChapterReviewDialog
          chapterId={reviewingChapter.id}
          chapterTitle={reviewingChapter.title}
          open={!!reviewingChapter}
          onOpenChange={(open) => !open && setReviewingChapter(null)}
          onSaved={() => {
            void refetch()
            void refetchExportStatus()
          }}
          hasNext={hasReviewNext}
          onSaveAndNext={() => goNextReview()}
        />
      )}

      <ConfirmDialog
        open={confirmDeleteNovel}
        onOpenChange={setConfirmDeleteNovel}
        title={t("common.deleteTitle")}
        description={t("novel.deleteNovelConfirm")}
        confirmLabel={t("novel.deleteNovel")}
        confirming={deleteNovelMutation.isPending}
        onConfirm={() => deleteNovelMutation.mutate()}
      />
      <ConfirmDialog
        open={confirmDeleteChapterId != null}
        onOpenChange={(open) => !open && setConfirmDeleteChapterId(null)}
        title={t("common.deleteTitle")}
        description={t("novel.deleteChapterConfirm")}
        confirmLabel={t("novel.deleteChapter")}
        confirming={deleteChapterMutation.isPending}
        onConfirm={() => {
          if (confirmDeleteChapterId != null) deleteChapterMutation.mutate(confirmDeleteChapterId)
        }}
      />
    </PageShell>
  )
}
