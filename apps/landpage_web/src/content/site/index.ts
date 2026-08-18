import type { Locale } from '../../lib/i18n';
import { ar } from './ar';
import { en } from './en';
import type { SiteCopy } from './types';

export type { SiteCopy };

export function getSiteCopy(locale: Locale): SiteCopy {
  return locale === 'ar' ? ar : en;
}
