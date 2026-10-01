import { useEffect, useRef } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bell, BellRing } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { useT } from "@/i18n"
import { crawlApi } from "../api"

const FOLLOWABLE = ["fully_crawled", "error", "translating", "ready_for_video"]
const PRESETS = ["nu_ke_cham", "nam_ke", "doi_thoai"] as const

export function FollowCard({ novelId, status }: { novelId: number; status: string }) {
  const t = useT()
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ["follows"],
    queryFn: crawlApi.listFollows,
    refetchInterval: (q) => (q.state.data?.items.some((f) => f.checking) ? 3000 : false),
  })
  const follow = data?.items.find((f) => f.novel_id === novelId)
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["follows"] })
    void queryClient.invalidateQueries({ queryKey: ["novel", novelId] })
  }
  const wasChecking = useRef(false)
  useEffect(() => {
    const now = follow?.checking ?? false
    if (wasChecking.current && !now) {
      void queryClient.invalidateQueries({ queryKey: ["novel", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
    }
    wasChecking.current = now
  }, [follow?.checking, novelId, queryClient])
  const onError = (e: Error) => toast.error(e.message)
  const save = useMutation({
    mutationFn: (body: { auto_translate: boolean; auto_audio: boolean; voice_preset: string }) =>
      crawlApi.follow(novelId, body),
    onSuccess: refresh,
    onError,
  })
  const remove = useMutation({ mutationFn: () => crawlApi.unfollow(novelId), onSuccess: refresh, onError })
  const check = useMutation({ mutationFn: () => crawlApi.checkFollow(novelId), onSuccess: refresh, onError })

  if (data == null || (!follow && !FOLLOWABLE.includes(status))) return null

  if (!follow) {
    return (
      <Card className="h-full">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex min-w-0 items-start gap-3">
            <Bell className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0">
              <p className="text-[15px] font-semibold">{t("novel.followTitle")}</p>
              <p className="text-[13px] text-muted-foreground">{t("novel.followHint")}</p>
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            disabled={save.isPending}
            onClick={() =>
              save.mutate({
                auto_translate: status === "translating" || status === "ready_for_video",
                auto_audio: false,
                voice_preset: "nam_ke",
              })
            }
          >
            {t("novel.follow")}
          </Button>
        </CardContent>
      </Card>
    )
  }

  const checking = follow.checking || check.isPending
  const last = follow.last_checked_at
    ? t("novel.followLast", { at: new Date(`${follow.last_checked_at}Z`).toLocaleString() })
    : t("novel.followNever")
  const result =
    follow.last_checked_at && !follow.last_error
      ? follow.last_new_chapters > 0
        ? t("novel.followNew", { n: follow.last_new_chapters })
        : t("novel.followNone")
      : null

  return (
    <Card className="h-full border-primary/25 bg-accent/50">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="flex min-w-0 items-start gap-3">
          <BellRing className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
          <div className="min-w-0 space-y-1">
            <p className="text-[15px] font-semibold">{t("novel.following")}</p>
            <p className="text-[13px] text-muted-foreground">
              {last}
              {result ? ` · ${result}` : null}
            </p>
            {follow.last_error ? <p className="text-[13px] text-destructive">{follow.last_error}</p> : null}
            <label className="flex items-center gap-2 pt-1 text-sm">
              <Checkbox
                checked={follow.auto_translate}
                disabled={save.isPending}
                onCheckedChange={(v) =>
                  save.mutate({
                    auto_translate: v === true,
                    auto_audio: follow.auto_audio,
                    voice_preset: follow.voice_preset || "nam_ke",
                  })
                }
              />
              {t("novel.followAutoTranslate")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={follow.auto_audio}
                disabled={save.isPending}
                onCheckedChange={(v) =>
                  save.mutate({
                    auto_translate: follow.auto_translate,
                    auto_audio: v === true,
                    voice_preset: follow.voice_preset || "nam_ke",
                  })
                }
              />
              {t("novel.followAutoAudio")}
            </label>
            {follow.auto_audio ? (
              <select
                aria-label={t("novel.pipelineVoice")}
                className="h-9 w-44 rounded-lg border border-input bg-card px-2.5 text-sm"
                value={PRESETS.includes(follow.voice_preset as (typeof PRESETS)[number]) ? follow.voice_preset : "nam_ke"}
                disabled={save.isPending}
                onChange={(e) =>
                  save.mutate({
                    auto_translate: follow.auto_translate,
                    auto_audio: true,
                    voice_preset: e.target.value,
                  })
                }
              >
                {PRESETS.map((id) => (
                  <option key={id} value={id}>
                    {t(`tts.preset_${id}`)}
                  </option>
                ))}
              </select>
            ) : null}
            {follow.tts_work_id != null ? (
              <Link to={`/tts/${follow.tts_work_id}`} className="text-[13px] font-semibold text-accent-foreground hover:underline">
                {t("novel.pipelineOpenAudio")}
              </Link>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={checking} onClick={() => check.mutate()}>
            {checking ? t("novel.followChecking") : t("novel.followCheckNow")}
          </Button>
          <Button size="sm" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
            {t("novel.unfollow")}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
