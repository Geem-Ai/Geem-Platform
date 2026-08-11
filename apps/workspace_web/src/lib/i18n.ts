import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import ar from '@/locales/ar.json';
import en from '@/locales/en.json';

export const LOCALE_STORAGE_KEY = 'geem-locale';
export type AppLocale = 'en' | 'ar';

export function getStoredLocale(): AppLocale {
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  return stored === 'ar' ? 'ar' : 'en';
}

export function applyDocumentLocale(locale: AppLocale): void {
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ar: { translation: ar },
  },
  lng: getStoredLocale(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

applyDocumentLocale(getStoredLocale());

i18n.on('languageChanged', (lng) => {
  applyDocumentLocale(lng === 'ar' ? 'ar' : 'en');
});

export default i18n;
