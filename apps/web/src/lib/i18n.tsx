import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type Language = 'vi' | 'en';
export type Translate = (vi: string, en: string) => string;
const storageKey = 'email-assistant-language';
const I18nContext = createContext({
  language: 'vi' as Language,
  locale: 'vi-VN',
  t: ((vi: string) => vi) as Translate,
  setLanguage: (_language: Language) => {},
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => {
    try { return localStorage.getItem(storageKey) === 'en' ? 'en' : 'vi'; }
    catch { return 'vi'; }
  });
  useEffect(() => {
    document.documentElement.lang = language;
    try { localStorage.setItem(storageKey, language); } catch { /* Storage can be disabled. */ }
  }, [language]);
  const t: Translate = (vi, en) => language === 'vi' ? vi : en;
  return <I18nContext.Provider value={{ language, locale: language === 'vi' ? 'vi-VN' : 'en-GB', t, setLanguage }}>{children}</I18nContext.Provider>;
}

export function useI18n() { return useContext(I18nContext); }
