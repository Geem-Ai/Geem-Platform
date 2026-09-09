import type { Locale } from '../lib/i18n';

type RoboticsRoadmapCopy = {
  eyebrow: string;
  status: string;
  title: string;
  description: string;
  diagramLabel: string;
  technology: string;
  hardware: string;
  product: string;
  illustrationNote: string;
  roadmapLabel: string;
  stages: {
    id: 'partnerships' | 'development' | 'launch';
    status: string;
    title: string;
    description: string;
  }[];
  launchNote: string;
  contact: string;
};

const en: RoboticsRoadmapCopy = {
  eyebrow: 'Geem robotics',
  status: 'In development',
  title: 'Geem robots for business',
  description:
    'We are developing business robots that combine Geem technology with partner hardware. We plan to launch our robotics products by the end of 2027.',
  diagramLabel: 'Geem technology and partner hardware combine in business robots currently in development.',
  technology: 'Geem technology',
  hardware: 'Partner hardware',
  product: 'Business robots',
  illustrationNote: 'Conceptual illustration of the technology and hardware model.',
  roadmapLabel: 'Robotics development roadmap',
  stages: [
    {
      id: 'partnerships',
      status: 'Confirmed',
      title: 'Hardware partnerships signed',
      description: 'We have signed agreements with robot hardware providers.',
    },
    {
      id: 'development',
      status: 'Underway',
      title: 'Product development underway',
      description: 'We are developing the products with Geem technology and partner hardware.',
    },
    {
      id: 'launch',
      status: 'Planned',
      title: 'Target launch by end 2027',
      description: 'Our planned launch window for Geem business robotics products.',
    },
  ],
  launchNote: 'Planned launch by the end of 2027',
  contact: 'Discuss your business need',
};

const ar: RoboticsRoadmapCopy = {
  eyebrow: 'روبوتات جيم',
  status: 'قيد التطوير',
  title: 'روبوتات جيم للأعمال',
  description:
    'نطوّر روبوتات للأعمال تجمع تقنية جيم مع أجهزة يوفّرها شركاؤنا، ونخطّط لإطلاقها بنهاية 2027.',
  diagramLabel: 'تقنية جيم وأجهزة الشركاء تجتمعان في روبوتات للأعمال قيد التطوير.',
  technology: 'تقنية جيم',
  hardware: 'أجهزة الشركاء',
  product: 'روبوتات للأعمال',
  illustrationNote: 'رسم توضيحي لفكرة الجمع بين التقنية والأجهزة.',
  roadmapLabel: 'مراحل تطوير روبوتات جيم',
  stages: [
    {
      id: 'partnerships',
      status: 'مؤكّد',
      title: 'اتفاقيات موقّعة مع مزوّدي الأجهزة',
      description: 'وقّعنا اتفاقيات مع شركات مزوّدة لأجهزة الروبوت.',
    },
    {
      id: 'development',
      status: 'جارٍ',
      title: 'تطوير المنتجات جارٍ',
      description: 'نعمل على تطوير المنتجات بتقنية جيم وأجهزة الشركاء.',
    },
    {
      id: 'launch',
      status: 'مخطّط',
      title: 'الإطلاق المستهدف بنهاية 2027',
      description: 'الموعد المخطّط لإطلاق منتجات روبوتات جيم للأعمال.',
    },
  ],
  launchNote: 'الإطلاق المخطّط بنهاية 2027',
  contact: 'ناقش احتياجات منشأتك',
};

export function getRoboticsRoadmapCopy(locale: Locale): RoboticsRoadmapCopy {
  return locale === 'en' ? en : ar;
}
