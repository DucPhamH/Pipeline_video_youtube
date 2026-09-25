import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { LOCALE_OPTIONS, useI18n } from "./index"
import type { Locale } from "./types"

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n()

  return (
    <Select value={locale} onValueChange={(v) => v && setLocale(v as Locale)}>
      <SelectTrigger className="h-8 w-[8.5rem]" aria-label={t("nav.language")}>
        <SelectValue>{(v: string) => t(`lang.${v}`)}</SelectValue>
      </SelectTrigger>
      <SelectContent align="end">
        {LOCALE_OPTIONS.map((code) => (
          <SelectItem key={code} value={code}>
            {t(`lang.${code}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
