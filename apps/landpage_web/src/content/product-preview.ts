import type { Locale } from '../lib/i18n';

type PreviewMode = {
  id: 'general' | 'expert' | 'action';
  label: string;
  name: string;
  prompt: string;
  answer: string;
  steps: { title: string; detail: string }[];
  tag: string;
};
type PreviewCopy = { label: string; tabsLabel: string; inputLabel: string; outputLabel: string; open: string; note: string; modes: PreviewMode[] };
const content: Record<Locale, PreviewCopy> = {
  en: {
    label: 'Interactive product tour', tabsLabel: 'Explore Geem capabilities', inputLabel: 'You', outputLabel: 'Geem', open: 'Open your workspace',
    note: 'Illustrative examples. Explore each experience.',
    modes: [
      { id: 'general', label: 'Everyday AI', name: 'Geem General', prompt: 'Help me turn an idea into a clear launch plan.', answer: 'Let’s give your idea a useful starting point.', tag: 'Write · Think · Create · Code', steps: [
        {title: 'Define the idea', detail: 'Who is it for, and what does it help them do?'},
        {title: 'Shape the first version', detail: 'Choose the essentials to test with your audience.'},
        {title: 'Plan the next step', detail: 'Set priorities, owners and a way to learn.'},
      ]},
      { id: 'expert', label: 'Your Experts', name: 'Operations Expert', prompt: 'Help our team prepare for a new supplier.', answer: 'An Expert brings your business context into the work.', tag: 'Your knowledge · Your instructions', steps: [
        {title: 'Use selected knowledge', detail: 'Work from the onboarding guide you provide.'},
        {title: 'Follow your instructions', detail: 'Organize the required information and responsibilities.'},
        {title: 'Make the next step clear', detail: 'Prepare a checklist for your team to review.'},
      ]},
      { id: 'action', label: 'Connected actions', name: 'Connected Expert', prompt: 'Help me request a different delivery date.', answer: 'Connect the conversation to your business systems.', tag: 'Configured integrations required', steps: [
        {title: 'Understand the request', detail: 'Use your policy and the details the user provides.'},
        {title: 'Check access and approval', detail: 'Request a permitted action through a connected tool.'},
        {title: 'Return the system result', detail: 'Report a confirmed change or explain the next step.'},
      ]},
    ],
  },
  ar: {
    label: 'جولة في قدرات جيم', tabsLabel: 'استكشف قدرات جيم', inputLabel: 'أنت', outputLabel: 'جيم', open: 'افتح مساحة عملك',
    note: 'أمثلة توضيحية للتعرّف على قدرات جيم.',
    modes: [
      { id: 'general', label: 'مهامك اليومية', name: 'جيم', prompt: 'ساعدني في تحويل فكرة إلى خطة إطلاق واضحة.', answer: 'لنحوّل فكرتك إلى خطوات واضحة.', tag: 'اكتب · فكّر · ابتكر · برمج', steps: [
        {title: 'حدّد الفكرة', detail: 'من تستهدف بفكرتك، وما الفائدة التي تقدّمها؟'},
        {title: 'صمّم النسخة الأولى', detail: 'اختر الأساسيات التي ستختبرها مع جمهورك.'},
        {title: 'خطّط للخطوة التالية', detail: 'حدّد الأولويات والمسؤوليات وكيف ستقيّم النتائج.'},
      ]},
      { id: 'expert', label: 'خبراؤك', name: 'خبير العمليات', prompt: 'ساعد فريقنا في الاستعداد للتعامل مع مورّد جديد.', answer: 'يستعين الخبير بمعرفة منشأتك لإرشاد فريقك.', tag: 'معرفتك · تعليماتك', steps: [
        {title: 'الاستناد إلى معرفتك', detail: 'يرجع إلى دليل تأهيل المورّدين الذي أضفته.'},
        {title: 'اتباع تعليماتك', detail: 'ينظّم المعلومات المطلوبة ويوضّح المسؤوليات.'},
        {title: 'تحديد الخطوة التالية', detail: 'يجهّز قائمة إجراءات يراجعها فريقك.'},
      ]},
      { id: 'action', label: 'إجراءات العمل', name: 'خبير متصل بأنظمتك', prompt: 'ساعدني في طلب تغيير موعد التوصيل.', answer: 'اربط المحادثة بأنظمة أعمالك.', tag: 'يتطلب إعداد التكاملات', steps: [
        {title: 'فهم الطلب', detail: 'يستند إلى سياساتك والتفاصيل التي يقدّمها المستخدم.'},
        {title: 'الصلاحيات والموافقات', detail: 'يطلب الإجراء عبر أداة متصلة، وفق الصلاحيات والموافقات المحددة.'},
        {title: 'نتيجة النظام', detail: 'يعرض التغيير الذي أكّده النظام، أو يوضّح الخطوة التالية.'},
      ]},
    ],
  },
};
export function getProductPreview(locale: Locale) { return content[locale]; }
