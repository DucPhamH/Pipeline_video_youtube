import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader, PageShell, SectionCard } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { translateApi } from "../api"
import { AiProvidersPanel } from "../components/AiProvidersPanel"
import { migrateLegacyProfilesOnce } from "../providerProfiles"

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
        <p className="text-sm text-destructive">{loadError}</p>
      </PageShell>
    )
  }

  if (!ready) {
    return (
      <PageShell>
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      </PageShell>
    )
  }

  return (
    <PageShell className="gap-6">
      <PageHeader
        eyebrow={
          <Link to="/translate" className="text-muted-foreground hover:text-foreground">
            {t("translate.backLibrary")}
          </Link>
        }
        title={t("translate.settings")}
        description={t("translate.translateSettingsHint")}
      />

      <AiProvidersPanel />

      <SectionCard
        title={t("translate.budgetSection")}
        description={t("translate.budgetSectionHint")}
        actions={
          <Button type="button" disabled={saving} onClick={() => void handleSaveBudget()}>
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        }
      >
        <div className="max-w-xs space-y-1.5">
          <Label htmlFor="tr-budget">{t("translate.setBudget")}</Label>
          <Input id="tr-budget" value={budget} onChange={(e) => setBudget(e.target.value)} className="h-10" />
        </div>
      </SectionCard>
    </PageShell>
  )
}
