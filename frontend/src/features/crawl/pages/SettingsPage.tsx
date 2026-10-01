import { useEffect, useState } from "react"
import { BellRing, Network, Save } from "lucide-react"
import { toast } from "sonner"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PageHeader, PageShell, SectionCard } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import { crawlApi } from "../api"
import { AiProvidersPanel } from "../../translate/components/AiProvidersPanel"
import { ApiTokenSettingsCard } from "@/components/ApiTokenPrompt"
import { PageSkeleton } from "@/components/Skeleton"
import { SettingRow } from "../components/SettingRow"

const WEBHOOK_KEY = "notify.webhook_url"

const PROXY_KEYS = [
  { key: "crawl.proxy", labelKey: "settings.proxyGlobal", hintKey: "settings.proxyGlobalHint" },
  { key: "crawl.proxy.vn", labelKey: "settings.proxyVn", hintKey: "settings.proxyRegionHint" },
  { key: "crawl.proxy.jp", labelKey: "settings.proxyJp", hintKey: "settings.proxyRegionHint" },
  { key: "crawl.proxy.kr", labelKey: "settings.proxyKr", hintKey: "settings.proxyRegionHint" },
  { key: "crawl.proxy.tw", labelKey: "settings.proxyTw", hintKey: "settings.proxyRegionHint" },
  { key: "crawl.proxy.cn", labelKey: "settings.proxyCn", hintKey: "settings.proxyRegionHint" },
] as const

type Draft = {
  webhook: string
  proxies: Record<string, string>
}

export function SettingsPage() {
  const t = useT()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  function load() {
    crawlApi
      .getSettings()
      .then((s) => {
        const proxies: Record<string, string> = {}
        for (const row of PROXY_KEYS) {
          proxies[row.key] = String(s.values[row.key] ?? "")
        }
        setDraft({
          webhook: String(s.values[WEBHOOK_KEY] ?? ""),
          proxies,
        })
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("app.unknownError")))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSave() {
    if (draft === null) return
    setSaving(true)
    try {
      const payload: Record<string, string> = {
        [WEBHOOK_KEY]: draft.webhook.trim(),
      }
      for (const row of PROXY_KEYS) {
        payload[row.key] = (draft.proxies[row.key] ?? "").trim()
      }
      const updated = await crawlApi.updateSettings(payload)
      const proxies: Record<string, string> = {}
      for (const row of PROXY_KEYS) {
        proxies[row.key] = String(updated.values[row.key] ?? "")
      }
      setDraft({
        webhook: String(updated.values[WEBHOOK_KEY] ?? ""),
        proxies,
      })
      toast.success(t("settings.saved"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  if (loadError && draft === null) {
    return (
      <PageShell>
        <PageHeader eyebrow={t("settings.eyebrow")} title={t("settings.title")} description={t("settings.alert")} />
        <Alert variant="destructive" className="border-danger/25 bg-danger-soft px-4 py-3">
          <AlertDescription className="text-danger">{loadError}</AlertDescription>
        </Alert>
        <ApiTokenSettingsCard />
      </PageShell>
    )
  }
  if (draft === null) {
    return (
      <PageShell>
        <PageHeader eyebrow={t("settings.eyebrow")} title={t("settings.title")} description={t("settings.alert")} />
        <PageSkeleton withHeader={false} />
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow={t("settings.eyebrow")}
        title={t("settings.title")}
        description={t("settings.alert")}
        primaryAction={
          <Button onClick={() => void handleSave()} disabled={saving}>
            <Save className="size-4" />
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        }
      />

      <ApiTokenSettingsCard />

      <AiProvidersPanel />

      <SectionCard
        title={
          <span className="flex items-center gap-2">
            <Network className="size-4 text-stage-collect" aria-hidden />
            {t("settings.proxySectionTitle")}
          </span>
        }
        description={t("settings.proxySectionHint")}
      >
        <div className="divide-y divide-border">
          {PROXY_KEYS.map((row) => (
            <SettingRow key={row.key} label={t(row.labelKey)} hint={t(row.hintKey)} htmlFor={row.key}>
              <Input
                id={row.key}
                type="text"
                value={draft.proxies[row.key] ?? ""}
                onChange={(e) =>
                  setDraft((prev) =>
                    prev ? { ...prev, proxies: { ...prev.proxies, [row.key]: e.target.value } } : prev,
                  )
                }
                placeholder="http://127.0.0.1:7890"
                className="h-10 w-full font-mono text-sm"
              />
            </SettingRow>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title={
          <span className="flex items-center gap-2">
            <BellRing className="size-4 text-stage-collect" aria-hidden />
            {t("settings.notifySectionTitle")}
          </span>
        }
        description={t("settings.notifySectionHint")}
      >
        <SettingRow label={t("settings.webhook")} hint={t("settings.webhookHint")} htmlFor={WEBHOOK_KEY}>
          <Input
            id={WEBHOOK_KEY}
            type="url"
            value={draft.webhook}
            onChange={(e) => setDraft((prev) => (prev ? { ...prev, webhook: e.target.value } : prev))}
            placeholder="https://discord.com/api/webhooks/…"
            className="h-10 w-full font-mono text-sm"
          />
        </SettingRow>
      </SectionCard>

      <div className="flex justify-end">
        <Button onClick={() => void handleSave()} disabled={saving} variant="outline">
          {saving ? t("common.saving") : t("common.save")}
        </Button>
      </div>
    </PageShell>
  )
}
