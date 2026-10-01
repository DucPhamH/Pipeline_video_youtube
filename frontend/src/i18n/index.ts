import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { en } from "./locales/en"
import { vi } from "./locales/vi"
import { zh } from "./locales/zh"
import { createTranslator } from "./translate"
import type { Locale, TranslateFn } from "./types"

const STORAGE_KEY = "crawl.locale"
const LOCALES: Record<Locale, typeof vi> = { vi, en, zh }

export const LOCALE_OPTIONS: Locale[] = ["vi", "en", "zh"]

function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === "vi" || saved === "en" || saved === "zh") return saved
  } catch {
    /* ignore */
  }
  const nav = typeof navigator !== "undefined" ? navigator.language.toLowerCase() : "vi"
  if (nav.startsWith("zh")) return "zh"
  if (nav.startsWith("en")) return "en"
  return "vi"
}

/** Translator dùng ngoài React (tầng API) — bám theo locale provider đang chọn. */
let activeT: TranslateFn = createTranslator(LOCALES[detectLocale()], vi)

export function translate(key: string, vars?: Record<string, string | number>): string {
  return activeT(key, vars)
}

type I18nContextValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: TranslateFn
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => detectLocale())

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : locale
  }, [locale])

  const t = useMemo(() => createTranslator(LOCALES[locale], vi), [locale])

  useEffect(() => {
    activeT = t
  }, [t])

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t])

  return createElement(I18nContext.Provider, { value }, children)
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error("useI18n must be used within I18nProvider")
  return ctx
}

export function useT(): TranslateFn {
  return useI18n().t
}
