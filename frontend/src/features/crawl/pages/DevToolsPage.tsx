import { useEffect, useMemo, useState } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"
import { PageHeader, PageShell, SectionCard, Toolbar } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import type { DryRunMode, DryRunResult } from "../../../api/types"
import { crawlApi } from "../api"

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
      <PageHeader title={t("dev.title")} description={t("dev.desc")} />

      <SectionCard title={t("dev.run")}>
        <form onSubmit={handleRun} className="space-y-3">
          <Toolbar>
            <Select value={sourceKey} onValueChange={(v) => v && setSourceKey(v)}>
              <SelectTrigger className="h-10 w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {sourceKeys.map((key) => (
                  <SelectItem key={key} value={key}>
                    {key}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={mode} onValueChange={(v) => v && setMode(v as DryRunMode)}>
              <SelectTrigger className="h-10 w-64">
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
            <Input
              type="text"
              required
              placeholder={t("dev.urlPlaceholder")}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="h-10 min-w-[16rem] flex-1"
            />
            <Button type="submit" disabled={running} className="h-10">
              {running ? t("dev.running") : t("dev.run")}
            </Button>
          </Toolbar>
        </form>
      </SectionCard>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {result ? (
        <SectionCard
          title={
            result.ok ? (
              <span className="text-emerald-700 dark:text-emerald-400">{t("dev.ok")}</span>
            ) : (
              <span className="text-destructive">{result.error ?? t("dev.fail")}</span>
            )
          }
        >
          {result.preview ? (
            <Table>
              <TableBody>
                {result.preview.map((item, i) => (
                  <TableRow key={i}>
                    <TableCell className="w-10 text-muted-foreground">{item.index ?? i + 1}</TableCell>
                    <TableCell className="font-medium">{item.title}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{item.url}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}

          {result.content_preview !== null && result.content_preview !== undefined ? (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                {t("dev.charsValidate", { count: result.content_length ?? 0 })}{" "}
                <span className={result.validation_passed ? "text-emerald-600" : "text-destructive"}>
                  {result.validation_passed ? t("dev.pass") : t("dev.noPass")}
                </span>
              </p>
              <Separator />
              <pre className="whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs">
                {result.content_preview}
              </pre>
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      {!result && !error ? (
        <Alert>
          <AlertDescription>{t("dev.empty")}</AlertDescription>
        </Alert>
      ) : null}
    </PageShell>
  )
}
