import type { Locale } from '../lib/i18n';

type ContactCopy = {
  eyebrow: string;
  title: string;
  introduction: string;
  salesEyebrow: string;
  salesTitle: string;
  salesDescription: string;
  emailSales: string;
  checklistTitle: string;
  checklist: string[];
  whatsappTitle: string;
  whatsappDescription: string;
  whatsappAction: string;
  phoneTitle: string;
  phoneDescription: string;
  customerEyebrow: string;
  customerTitle: string;
  customerDescription: string;
  login: string;
  generalTitle: string;
  generalDescription: string;
  companyTitle: string;
  companyDescription: string;
};

const en: ContactCopy = {
  eyebrow: 'Contact GEEM',
  title: 'Let’s put AI to work for your organization',
  introduction: 'Tell us what you want to improve. We can discuss how GEEM connects your knowledge, Experts, channels and systems.',
  salesEyebrow: 'For your business',
  salesTitle: 'Talk to our sales team',
  salesDescription: 'Explore GEEM cloud or tailored infrastructure we provide at your site. Discuss integrations, expected usage, setup and operating costs.',
  emailSales: 'Email sales',
  checklistTitle: 'A useful starting point',
  checklist: ['Your organization and team', 'The workflow you want to improve', 'Your knowledge sources, channels and systems', 'Preferred deployment and expected usage'],
  whatsappTitle: 'Connect on WhatsApp',
  whatsappDescription: 'Start a conversation about your business needs.',
  whatsappAction: 'Open WhatsApp',
  phoneTitle: 'Call our team',
  phoneDescription: 'Speak with DALSEEN, the company behind GEEM.',
  customerEyebrow: 'Existing customers',
  customerTitle: 'Already using GEEM?',
  customerDescription: 'Sign in to your workspace to continue setup and access support.',
  login: 'Workspace login',
  generalTitle: 'General inquiries',
  generalDescription: 'For company questions and other inquiries, email our team.',
  companyTitle: 'Built by DALSEEN',
  companyDescription: 'GEEM is developed and operated by DALSEEN, based in Madinah, Saudi Arabia.',
};

const ar: ContactCopy = {
  eyebrow: 'تواصل مع GEEM',
  title: 'لنتحدث عن توظيف الذكاء الاصطناعي في مؤسستك',
  introduction: 'حدّثنا عمّا تريد تحسينه، لنناقش كيف يربط GEEM معرفة مؤسستك بقنواتها وأنظمتها عبر خبراء متخصصين.',
  salesEyebrow: 'لاحتياجات مؤسستك',
  salesTitle: 'تواصل مع فريق المبيعات',
  salesDescription: 'ناقش التشغيل عبر سحابة GEEM أو بنية مخصصة نوفّرها في موقعك، والتكاملات وحجم الاستخدام المتوقع وكلفة التجهيز والتشغيل.',
  emailSales: 'راسل فريق المبيعات',
  checklistTitle: 'لنبدأ من احتياجك',
  checklist: ['مؤسستك والفريق الذي سيستخدم GEEM', 'إجراءات العمل التي تريد تحسينها', 'مصادر المعرفة والقنوات والأنظمة التي تستخدمها', 'بيئة التشغيل المفضلة وحجم الاستخدام المتوقع'],
  whatsappTitle: 'تواصل عبر WhatsApp',
  whatsappDescription: 'ابدأ محادثة معنا حول احتياجات مؤسستك.',
  whatsappAction: 'افتح WhatsApp',
  phoneTitle: 'اتصل بفريقنا',
  phoneDescription: 'تواصل مع DALSEEN، الشركة المطوّرة لـ GEEM.',
  customerEyebrow: 'للعملاء الحاليين',
  customerTitle: 'تستخدم GEEM بالفعل؟',
  customerDescription: 'سجّل الدخول إلى مساحة عملك لمتابعة الإعداد والحصول على الدعم.',
  login: 'الدخول إلى مساحة العمل',
  generalTitle: 'الاستفسارات العامة',
  generalDescription: 'للاستفسارات عن الشركة والمواضيع الأخرى، راسل فريقنا.',
  companyTitle: 'تطوّره DALSEEN',
  companyDescription: 'GEEM منتج تطوّره وتشغّله DALSEEN، ومقرها المدينة المنورة في المملكة العربية السعودية.',
};

export function getContactCopy(locale: Locale): ContactCopy {
  return locale === 'ar' ? ar : en;
}
