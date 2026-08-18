import type { Locale } from './i18n';
import { absoluteUrl, getSiteConfig, localizedPath } from './site';

export type SeoInput = {
  locale: Locale;
  title: string;
  description: string;
  path?: string;
  robots?: string;
  ogImage?: string;
  ogImageAlt?: string;
  ogImageType?: string;
  ogImageWidth?: number;
  ogImageHeight?: number;
};

export function buildSeo(input: SeoInput) {
  const { ogImageUrl, ogImageType, ogImageWidth, ogImageHeight } = getSiteConfig();
  const path = input.path ?? '';
  const canonical = absoluteUrl(input.locale, path);
  const alternateAr = absoluteUrl('ar', path);
  const alternateEn = absoluteUrl('en', path);
  const defaultImageAlt =
    input.locale === 'ar'
      ? 'هوية جيم البصرية مع خبير ذكاء اصطناعي متصل بمعرفة المنشأة وأنظمتها فوق أفق سعودي'
      : 'Geem AI Expert connected to an organization’s knowledge and systems over a Saudi skyline';

  return {
    title: input.title,
    description: input.description,
    canonical,
    robots: input.robots ?? 'index,follow',
    ogImage: input.ogImage ?? ogImageUrl,
    ogImageAlt: input.ogImageAlt ?? defaultImageAlt,
    ogImageType: input.ogImageType ?? ogImageType,
    ogImageWidth: input.ogImageWidth ?? ogImageWidth,
    ogImageHeight: input.ogImageHeight ?? ogImageHeight,
    alternateAr,
    alternateEn,
    xDefault: alternateAr,
    locale: input.locale,
    ogLocale: input.locale === 'ar' ? 'ar_SA' : 'en_US',
    ogLocaleAlt: input.locale === 'ar' ? 'en_US' : 'ar_SA',
  };
}

export function organizationJsonLd() {
  const { siteUrl } = getSiteConfig();
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'Geem',
    legalName: 'Dal Seen Information Technology Company',
    url: siteUrl,
    logo: `${siteUrl}/favicon.svg`,
    email: 'info@dalseen.sa',
    telephone: '+966920014079',
    address: {
      '@type': 'PostalAddress',
      streetAddress: 'King Khalid Road, Al Aqoul',
      addressLocality: 'Medina',
      addressCountry: 'SA',
    },
    sameAs: ['https://dalseen.sa'],
  };
}

export function softwareApplicationJsonLd(locale: Locale) {
  const { siteUrl } = getSiteConfig();
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Geem',
    applicationCategory: 'BusinessApplication',
    operatingSystem: 'Web',
    url: `${siteUrl}/${locale}`,
    description:
      locale === 'ar'
        ? 'منصة جيم: خبراء ذكاء اصطناعي مبنيون على معرفة منشأتك، عبر الدردشة وواتساب والموقع وأنظمتك.'
        : 'Geem: AI Experts grounded in your organization’s knowledge, available through chat, WhatsApp, your website, and your systems.',
    publisher: {
      '@type': 'Organization',
      name: 'Dal Seen Information Technology Company',
    },
  };
}

export { localizedPath };
