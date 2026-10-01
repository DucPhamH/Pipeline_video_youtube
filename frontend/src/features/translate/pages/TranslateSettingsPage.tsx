import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader, PageShell, SectionCard } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { translateApi } from "../api"
import { AiProvidersPanel } from "../components/AiProvidersPanel"
import { AiUsagePanel } from "@/features/ai/AiUsagePanel"
import { migrateLegacyProfilesOnce } from "../providerProfiles"
import { PageSkeleton } from "@/components/Skeleton"
import { EmptyState } from "@/components/EmptyState"
import { AlertTriangle, Save } from "lucide-react"

export function TranslateSettingsPage() {
  const t = useT()
  const [budget, setBudget] = useState("0")
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    translateApi
      .getSettings()
      .then((s) => {
        setBudget(String(s.values["translate.budget_usd_per_job"] ?? "0"))
        setReady(true)
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : t("app.unknownError"))
        setReady(true)
      })
    void migrateLegacyProfilesOnce(translateApi.createAiProvider).then((n) => {
      if (n > 0) toast.message(t("translate.aiProviderMigrated", { count: n }))
    })
  }, [t])

  async function handleSaveBudget() {
    setSaving(true)
    try {
      await translateApi.updateSettings({
        "translate.budget_usd_per_job": Number(budget) || 0,
      })
      toast.success(t("translate.settingsSaved"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <PageShell>
        <PageHeader
          breadcrumbs={[{ label: t("translate.title"), to: "/translate" }, { label: t("translate.settings") }]}
          title={t("translate.settings")}
        />
        <EmptyState icon={AlertTriangle} tone="neutral" title={loadError} />
      </PageShell>
    )
  }

  if (!ready) {
    return (
      <PageShell>
        <PageSkeleton />
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        breadcrumbs={[{ label: t("translate.title"), to: "/translate" }, { label: t("translate.settings") }]}
        eyebrow={t("translate.hub.eyebrow")}
        stage="translate"
        title={t("translate.settings")}
        description={t("translate.translateSettingsHint")}
      />

      <AiProvidersPanel />

      <AiUsagePanel />

      <SectionCard
        title={t("translate.budgetSection")}
        description={t("translate.budgetSectionHint")}
        actions={
          <Button type="button" size="sm" disabled={saving} onClick={() => void handleSaveBudget()}>
            <Save aria-hidden />
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        }
      >
        <div className="max-w-xs space-y-1.5">
          <Label htmlFor="tr-budget">{t("translate.setBudget")}</Label>
          <div className="relative">
            <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 font-mono text-sm text-muted-foreground">
              $
            </span>
            <Input
              id="tr-budget"
              inputMode="decimal"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              className="h-10 pl-7 font-mono"
            />
          </div>
        </div>
      </SectionCard>
    </PageShell>
  )
}
