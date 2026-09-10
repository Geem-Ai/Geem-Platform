import type { Locale } from '../lib/i18n';

type ProductEcosystemItem = {
  id: 'erp' | 'platform' | 'qaf-noon';
  name: string;
  description: string;
};

export type ProductEcosystemCopy = {
  status: string;
  title: string;
  description: string;
  products: ProductEcosystemItem[];
  valueTitle: string;
  value: string;
};

const en: ProductEcosystemCopy = {
  status: 'Working today',
  title: 'GEEM inside existing products',
  description: 'GEEM is embedded and functioning in these products today, within their existing workflows.',
  products: [
    {
      id: 'erp',
      name: 'DALSEEN ERP',
      description: 'AI within the existing business system.',
    },
    {
      id: 'platform',
      name: 'DALSEEN Platform',
      description: 'AI as part of the platform experience.',
    },
    {
      id: 'qaf-noon',
      name: 'Qaf Noon',
      description: 'AI within a specialist product’s workflows.',
    },
  ],
  valueTitle: 'Build on working integrations',
  value: 'These integrations provide a starting point to reduce repeated integration work and adopt AI one workflow at a time.',
};

const ar: ProductEcosystemCopy = {
  status: 'يعمل اليوم',
  title: 'GEEM ضمن منتجات قائمة',
  description: 'يعمل GEEM اليوم داخل هذه المنتجات، ضمن إجراءات العمل القائمة فيها.',
  products: [
    {
      id: 'erp',
      name: 'DALSEEN ERP',
      description: 'ذكاء اصطناعي ضمن نظام الأعمال القائم.',
    },
    {
      id: 'platform',
      name: 'DALSEEN Platform',
      description: 'ذكاء اصطناعي ضمن تجربة استخدام المنصة.',
    },
    {
      id: 'qaf-noon',
      name: 'Qaf Noon',
      description: 'ذكاء اصطناعي ضمن إجراءات منتج متخصص.',
    },
  ],
  valueTitle: 'البناء على تكاملات تعمل بالفعل',
  value: 'تمنح هذه التكاملات نقطة انطلاق لتقليل تكرار أعمال الربط وتبنّي الذكاء الاصطناعي تدريجيًا، مسار عمل تلو الآخر.',
};

export function getProductEcosystemCopy(locale: Locale): ProductEcosystemCopy {
  return locale === 'en' ? en : ar;
}
