import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useT } from "@/i18n"
import { queryKeys } from "@/lib/query-client"
import { ApiError } from "../../../api/client"
import { crawlApi } from "../api"

const POLL_INTERVAL_MS = 3000
const NONE_VALUE = "__none__"
/** Mỗi site có ~5–15 thể loại — load hết 1 lần cho ô Select, không phân trang UI. */
const GENRE_SELECT_LIMIT = 100

/**
 * Trạng thái + hành động "Quét nhiều" của 1 site. Dùng ở trang site để nút
 * "Quét ngay" nằm ở PageHeader (hành động chính) còn thẻ quét ở tab Bulk.
 */
export function useGenreScan(sourceKey: string) {
  const t = useT()
  const queryClient = useQueryClient()
  const genreQueryKey = { sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }

  const query = useQuery({
    queryKey: queryKeys.genres(genreQueryKey),
    queryFn: () => crawlApi.listGenres(genreQueryKey),
    refetchInterval: (q) =>
      q.state.data?.items.some((g) => g.last_run_status === "running") ? POLL_INTERVAL_MS : false,
  })
  const genres = query.data?.items ?? null
  const active = genres?.find((g) => g.enabled) ?? null
  const isRunning = active?.last_run_status === "running"

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: queryKeys.genres(genreQueryKey) })
  const onError = (err: unknown) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))

  const selectMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.toggleGenre(genreId, true),
    onSuccess: invalidate,
    onError,
  })
  const deselectMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.toggleGenre(genreId, false),
    onSuccess: invalidate,
    onError,
  })
  const runMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.runGenreNow(genreId),
    onSuccess: () => {
      invalidate()
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
      toast.message(t("site.scanStarted"))
    },
    onError,
  })
  const cancelMutation = useMutation({
    mutationFn: (genreId: number) => crawlApi.cancelGenreRun(genreId),
    onSuccess: () => {
      invalidate()
      toast.message(t("site.scanCancelSent"))
    },
    onError,
  })

  return {
    query,
    genres,
    active,
    isRunning,
    select: (id: string | null) => {
      if (!genres) return
      if (!id || id === NONE_VALUE) {
        if (active) deselectMutation.mutate(active.id)
        return
      }
      selectMutation.mutate(Number(id))
    },
    run: () => active && runMutation.mutate(active.id),
    cancel: () => active && cancelMutation.mutate(active.id),
    runPending: runMutation.isPending,
    cancelPending: cancelMutation.isPending,
  }
}

export type GenreScan = ReturnType<typeof useGenreScan>

