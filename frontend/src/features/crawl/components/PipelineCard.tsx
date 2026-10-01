import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AudioLines } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useT } from "@/i18n"
import { crawlApi, type Pipeline } from "../api"

const PRESETS = ["nu_ke_cham", "nam_ke", "doi_thoai"] as const
const ACTIVE = new Set(["smoothing", "translating", "speaking"])

function stageLabel(t: (key: string) => string, stage: string): string {
  const key = `novel.pipelineStage_${stage}`
  const label = t(key)
  return label === key ? stage : t(key)
}

export function PipelineCard({ novelId, enabled }: { novelId: number; enabled: boolean }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [preset, setPreset] = useState("nam_ke")
  const { data } = useQuery({
    queryKey: ["pipelines"],
    queryFn: crawlApi.listPipelines,
    refetchInterval: (q) => (q.state.data?.items.some((p) => ACTIVE.has(p.stage)) ? 3000 : false),
  })
  const pipeline = data?.items.find((p) => p.novel_id === novelId)
  const running = pipeline != null && ACTIVE.has(pipeline.stage)
  const start = useMutation({
    mutationFn: () => crawlApi.startPipeline(novelId, preset),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipelines"] })
      void queryClient.invalidateQueries({ queryKey: ["novel", novelId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (data == null || (!enabled && !pipeline)) return null

  return (
    <Card className={running ? "h-full border-primary/25 bg-accent/50" : "h-full"}>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="flex min-w-0 items-start gap-3">
          <AudioLines className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
          <div className="min-w-0 space-y-1">
            <p className="text-[15px] font-semibold">{t("novel.pipelineTitle")}</p>
            <p className="text-[13px] text-muted-foreground">{t("novel.pipelineHint")}</p>
            {pipeline ? <Status pipeline={pipeline} /> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label={t("novel.pipelineVoice")}
            value={preset}
            disabled={running || start.isPending}
            onChange={(e) => setPreset(e.target.value)}
            className="h-9 w-44 rounded-lg border border-input bg-card px-2.5 text-sm"
          >
            {PRESETS.map((id) => (
              <option key={id} value={id}>
                {t(`tts.preset_${id}`)}
              </option>
            ))}
          </select>
          <Button size="sm" disabled={!enabled || running || start.isPending} onClick={() => start.mutate()}>
            {running || start.isPending ? stageLabel(t, pipeline?.stage ?? "smoothing") : t("novel.pipelineRun")}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function Status({ pipeline }: { pipeline: Pipeline }) {
  const t = useT()
  return (
    <p className="text-[13px]">
      <span className={pipeline.stage === "error" ? "text-destructive" : "text-muted-foreground"}>
        {stageLabel(t, pipeline.stage)}
        {pipeline.error ? `: ${pipeline.error}` : ""}
      </span>
      {pipeline.translate_work_id != null ? (
        <>
          {" · "}
          <Link to={`/translate/${pipeline.translate_work_id}`} className="font-semibold text-accent-foreground hover:underline">
            {t("novel.pipelineOpenTranslate")}
          </Link>
        </>
      ) : null}
      {pipeline.tts_work_id != null ? (
        <>
          {" · "}
          <Link to={`/tts/${pipeline.tts_work_id}`} className="font-semibold text-accent-foreground hover:underline">
            {t("novel.pipelineOpenAudio")}
          </Link>
        </>
      ) : null}
    </p>
  )
}
