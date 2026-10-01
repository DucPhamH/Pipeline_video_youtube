import { useEffect, useMemo, useState } from "react"
import { FlaskConical, Play } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { EmptyState } from "@/components/EmptyState"
import { PageHeader, PageShell, SectionCard } from "@/components/PageChrome"
import { StatusPill } from "@/components/StatusPill"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import type { DryRunMode, DryRunResult } from "../../../api/types"
import { crawlApi } from "../api"
import { SettingRow } from "../components/SettingRow"

export function DevToolsPage() {
  const t = useT()
  const [sourceKeys, setSourceKeys] = useState<string[]>([])
  const [sourceKey, setSourceKey] = useState("")
  const [mode, setMode] = useState<DryRunMode>("genre")
  const [url, setUrl] = useState("")
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<DryRunResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const modeLabels = useMemo(
    () =>
      ({
        genre: t("dev.modeGenre"),
        chapters: t("dev.modeChapters"),
        content: t("dev.modeContent"),
      }) as Record<DryRunMode, string>,
    [t],
  )

  useEffect(() => {
    crawlApi
      .listSites({ limit: 100 })
      .then((data) => {
        const keys = data.items.map((s) => s.key)
        setSourceKeys(keys)
        setSourceKey(keys[0] ?? "")
      })
      .catch(() => setSourceKeys([]))
  }, [])

  async function handleRun(e: React.FormEvent) {
    e.preventDefault()
    if (!sourceKey || !url.trim()) return
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      setResult(await crawlApi.dryRun(sourceKey, url.trim(), mode))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setRunning(false)
    }
  }

  return (
    <PageShell>
      <PageHeader eyebrow={t("dev.eyebrow")} stage="collect" title={t("dev.title")} description={t("dev.desc")} />

      <SectionCard title={t("dev.formTitle")} description={t("dev.formHint")}>
        <form onSubmit={handleRun}>
          <div className="divide-y divide-border">
            <SettingRow label={t("dev.source")} htmlFor="dev-source">
              <Select value={sourceKey} onValueChange={(v) => v && setSourceKey(v)}>
                <SelectTrigger id="dev-source" className="h-10 w-full sm:w-64">
                  <SelectValue>{(v: string) => v || "—"}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {sourceKeys.map((key) => (
                    <SelectItem key={key} value={key}>
                      {key}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </SettingRow>
            <SettingRow label={t("dev.mode")} htmlFor="dev-mode">
              <Select value={mode} onValueChange={(v) => v && setMode(v as DryRunMode)}>
                <SelectTrigger id="dev-mode" className="h-10 w-full sm:w-64">
                  <SelectValue>{(v: DryRunMode) => modeLabels[v] ?? v}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(modeLabels) as DryRunMode[]).map((m) => (
                    <SelectItem key={m} value={m}>
                      {modeLabels[m]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </SettingRow>
            <SettingRow label={t("dev.url")} htmlFor="dev-url">
              <Input
                id="dev-url"
                type="text"
                required
                inputMode="url"
                placeholder={t("dev.urlPlaceholder")}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="h-10 w-full font-mono text-sm"
              />
            </SettingRow>
          </div>
          <div className="mt-5 flex justify-end">
            <Button type="submit" disabled={running}>
              <Play className="size-4" />
              {running ? t("dev.running") : t("dev.run")}
            </Button>
          </div>
        </form>
      </SectionCard>

      {error ? (
        <Alert variant="destructive" className="border-danger/25 bg-danger-soft px-4 py-3">
          <AlertDescription className="text-danger">{error}</AlertDescription>
        </Alert>
      ) : null}

      {result ? (
        <SectionCard
          title={
            <span className="flex flex-wrap items-center gap-2">
              {t("dev.result")}
              <StatusPill
                status={result.ok ? "succeeded" : "failed"}
                label={result.ok ? t("dev.ok") : t("dev.fail")}
              />
            </span>
          }
          description={!result.ok && result.error ? result.error : undefined}
        >
          {result.preview ? (
            <ol className="divide-y rounded-xl border">
              {result.preview.map((item, i) => (
                <li key={i} className="flex flex-col gap-0.5 px-3 py-2.5 sm:flex-row sm:items-baseline sm:gap-3">
                  <span className="w-10 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                    {item.index ?? i + 1}
                  </span>
                  <span className="min-w-0 font-medium">{item.title}</span>
                  <span className="min-w-0 truncate font-mono text-xs text-muted-foreground sm:ml-auto sm:max-w-[45%]" title={item.url}>
                    {item.url}
                  </span>
                </li>
              ))}
            </ol>
          ) : null}

          {result.content_preview !== null && result.content_preview !== undefined ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground">
                <span>{t("dev.charsValidate", { count: result.content_length ?? 0 })}</span>
                <StatusPill
                  status={result.validation_passed ? "succeeded" : "failed"}
                  label={result.validation_passed ? t("dev.pass") : t("dev.noPass")}
                />
              </div>
              <pre className="max-h-[60vh] overflow-auto rounded-xl bg-muted p-4 text-sm leading-relaxed whitespace-pre-wrap">
                {result.content_preview}
              </pre>
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      {!result && !error ? (
        <div className="rounded-2xl border border-dashed bg-card">
          <EmptyState icon={FlaskConical} tone="collect" title={t("dev.emptyTitle")} hint={t("dev.empty")} />
        </div>
      ) : null}
    </PageShell>
  )
}
