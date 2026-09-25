import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader, PageShell, SectionCard } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import { crawlApi } from "../api"
import { AiProvidersPanel } from "../../translate/components/AiProvidersPanel"

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
        <PageHeader title={t("settings.title")} description={t("settings.alert")} />
        <p className="text-sm text-destructive">{loadError}</p>
      </PageShell>
    )
  }
  if (draft === null) {
    return (
      <PageShell>
        <PageHeader title={t("settings.title")} description={t("settings.alert")} />
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      </PageShell>
    )
  }

  return (
    <PageShell className="gap-6">
      <PageHeader
        title={t("settings.title")}
        description={t("settings.alert")}
        actions={
          <Button onClick={() => void handleSave()} disabled={saving}>
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        }
      />

      <AiProvidersPanel />

      <SectionCard
        title={t("settings.proxySectionTitle")}
        description={t("settings.proxySectionHint")}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          {PROXY_KEYS.map((row) => (
            <div key={row.key} className="space-y-1.5">
              <Label htmlFor={row.key}>{t(row.labelKey)}</Label>
              <Input
                id={row.key}
                type="text"
                value={draft.proxies[row.key] ?? ""}
                onChange={(e) =>
                  setDraft((prev) =>
                    prev
                      ? {
                          ...prev,
                          proxies: { ...prev.proxies, [row.key]: e.target.value },
                        }
                      : prev,
                  )
                }
                placeholder="http://127.0.0.1:7890"
                className="h-10 w-full font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">{t(row.hintKey)}</p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title={t("settings.webhook")} description={t("settings.webhookHint")}>
        <Input
          id={WEBHOOK_KEY}
          type="url"
          value={draft.webhook}
          onChange={(e) => setDraft((prev) => (prev ? { ...prev, webhook: e.target.value } : prev))}
          placeholder="https://discord.com/api/webhooks/…"
          className="h-10 w-full max-w-xl"
        />
      </SectionCard>
    </PageShell>
  )
}
