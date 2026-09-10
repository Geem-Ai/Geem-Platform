import type { Locale } from './i18n';
import { absoluteUrl, getSiteConfig, localizedPath } from './site';
import { company } from './company';

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
    xDefault: alternateEn,
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
    legalName: company.legalNameEn,
    url: siteUrl,
    logo: `${siteUrl}/favicon.svg`,
    email: company.emails.info,
    telephone: company.phoneTel,
    address: {
      '@type': 'PostalAddress',
      streetAddress: 'Prince Mohammed bin Abdulaziz Road',
      addressLocality: 'Madinah',
      postalCode: '42311',
      addressCountry: 'SA',
    },
    sameAs: [company.companySite],
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
        ? 'جيم: ذكاء اصطناعي للكتابة والبرمجة وخبراء متصلون بمعرفة المنشأة وأنظمتها، عبر الدردشة وWhatsApp والموقع، مع خيارات تشغيل على سحابة جيم أو داخل المنشأة.'
        : 'GEEM: AI for writing, coding and Experts connected to business knowledge and systems, across chat, WhatsApp and websites. Run on GEEM cloud or at your premises.',
    publisher: {
      '@type': 'Organization',
      name: company.legalNameEn,
    },
  };
}

export { localizedPath };
