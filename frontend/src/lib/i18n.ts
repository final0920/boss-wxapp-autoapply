import { createContext, useContext, useState, useCallback, createElement, type ReactNode } from 'react'
import { zh } from './locales/zh'
import { en } from './locales/en'
import type { I18nKeys } from './locales/zh'

export type Locale = 'zh' | 'en'

const locales: Record<Locale, I18nKeys> = { zh, en }

interface I18nContextValue {
  locale: Locale
  t: I18nKeys
  setLocale: (l: Locale) => void
}

const I18nContext = createContext<I18nContextValue>({
  locale: 'zh',
  t: zh,
  setLocale: () => {},
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    const saved = localStorage.getItem('locale') as Locale | null
    return saved ?? 'zh'
  })

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l)
    localStorage.setItem('locale', l)
  }, [])

  return createElement(
    I18nContext.Provider,
    { value: { locale, t: locales[locale], setLocale } },
    children,
  )
}

export function useI18n() {
  return useContext(I18nContext)
}
