import type { Locale } from '../lib/i18n';

export type PlatformFoundationCopy = {
  eyebrow: string;
  title: string;
  description: string;
  infrastructureLabel: string;
  infrastructureTitle: string;
  infrastructureDescription: string;
  diagramLabel: string;
  modelsLabel: string;
  modelsTitle: string;
  modelsDescription: string;
  platformLabel: string;
  platformTitle: string;
  platformDescription: string;
  controls: string[];
  outputs: { id: 'general' | 'experts' | 'actions'; title: string; description: string }[];
  note: string;
  valuesLabel: string;
  values: string[];
};

const en: PlatformFoundationCopy = {
  eyebrow: 'The foundation behind Geem',
  title: 'Our AI model and our own infrastructure',
  description:
    'Geem is our fine-tuned AI model, built on multiple underlying models. We run open-source models locally on Geem-owned GPUs, using different model weights as we continue developing and refining the Geem model.',
  infrastructureLabel: 'Geem infrastructure',
  infrastructureTitle: 'Models running on our own GPUs',
  infrastructureDescription:
    'Geem operates these models on its own servers and infrastructure.',
  diagramLabel: 'From the Geem model to business AI capabilities',
  modelsLabel: 'Our fine-tuned model',
  modelsTitle: 'The Geem AI model',
  modelsDescription: 'Built on multiple underlying models. Development continues.',
  platformLabel: 'Managed by Geem',
  platformTitle: 'One connected AI platform',
  platformDescription: 'Connecting AI capabilities to your workspace and business context.',
  controls: ['Workspace knowledge', 'Access and usage controls', 'Connected tools'],
  outputs: [
    { id: 'general', title: 'General AI', description: 'Explore ideas, write and understand information.' },
    { id: 'experts', title: 'Business Experts', description: 'Put your business knowledge to work through Experts across your channels.' },
    { id: 'actions', title: 'Connected actions', description: 'Look up information or request a permitted system action.' },
  ],
  note: 'Our platform brings the Geem model, workspace knowledge and connected tools into one experience.',
  valuesLabel: 'What this means for your business',
  values: [
    'Start everyday AI work in a shared, familiar workspace.',
    'Give each Expert the knowledge and purpose your team needs.',
    'Keep system access and action approvals in your connected workflow.',
    'Reduce repeated setup by reusing knowledge and integrations across suitable workflows.',
  ],
};

const ar: PlatformFoundationCopy = {
  eyebrow: 'التقنية وراء جيم',
  title: 'نموذج نطوّره، وبنية تحتية نمتلكها',
  description:
    'جيم نموذج ذكاء اصطناعي طوّرناه بالاعتماد على عدة نماذج أساسية، وخصّصناه بتدريب إضافي. نشغّل نماذج مفتوحة المصدر محليًا على وحدات معالجة رسومية نمتلكها، ونستخدم أوزانًا مختلفة للنماذج مع مواصلة تطوير جيم وتحسينه.',
  infrastructureLabel: 'بنية جيم التحتية',
  infrastructureTitle: 'نماذج تعمل على معالجاتنا الرسومية',
  infrastructureDescription:
    'تعمل هذه النماذج على خوادم جيم وبنيتها التحتية.',
  diagramLabel: 'كيف يدعم نموذج جيم قدرات المنصة',
  modelsLabel: 'نموذج نطوّره باستمرار',
  modelsTitle: 'نموذج جيم للذكاء الاصطناعي',
  modelsDescription: 'نطوّره بالاعتماد على عدة نماذج أساسية.',
  platformLabel: 'بإدارة جيم',
  platformTitle: 'منصة واحدة لقدرات جيم',
  platformDescription: 'تربط قدرات الذكاء الاصطناعي بمساحة عملك ومعرفة منشأتك.',
  controls: ['معرفة منشأتك', 'إدارة الصلاحيات والاستخدام', 'الأدوات المتصلة'],
  outputs: [
    { id: 'general', title: 'مساعدة عامة', description: 'طوّر أفكارك، وصغ محتواك، وافهم المعلومات.' },
    { id: 'experts', title: 'خبراء الأعمال', description: 'وظّف معرفة منشأتك عبر خبراء يخدمون قنواتك المختلفة.' },
    { id: 'actions', title: 'إجراءات عبر أنظمتك', description: 'استعلم عن بيانات أنظمتك أو اطلب تنفيذ إجراء تسمح به صلاحياتك.' },
  ],
  note: 'تجمع منصتنا نموذج جيم ومعرفة منشأتك وأدواتها المتصلة في تجربة واحدة.',
  valuesLabel: 'ما الذي يقدّمه ذلك لمنشأتك؟',
  values: [
    'أنجز مهامك اليومية بمساعدة الذكاء الاصطناعي في مساحة عمل مشتركة.',
    'حدّد مهمة كل خبير وزوّده بالمعرفة التي يحتاجها فريقك.',
    'حافظ على صلاحيات الأنظمة والموافقات المطلوبة عند ربط إجراءات العمل.',
    'قلّل تكرار الإعداد بالاستفادة من المعرفة والتكاملات في إجراءات العمل المناسبة.',
  ],
};

export function getPlatformFoundationCopy(locale: Locale): PlatformFoundationCopy {
  return locale === 'en' ? en : ar;
}
