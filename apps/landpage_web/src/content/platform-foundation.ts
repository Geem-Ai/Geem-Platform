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
  eyebrow: 'The foundation behind GEEM',
  title: 'Our AI model and our own infrastructure',
  description:
    'GEEM is our fine-tuned AI model, built on multiple underlying models. We run open-source models with different weights on our own GPUs and servers, and continue developing GEEM for business needs.',
  infrastructureLabel: 'Deployment and infrastructure',
  infrastructureTitle: 'GEEM cloud or your premises',
  infrastructureDescription:
    'Use GEEM cloud or tailored infrastructure we provide at your site. We plan GPU, storage and network capacity around your workload.',
  diagramLabel: 'From the GEEM model to business AI capabilities',
  modelsLabel: 'Our fine-tuned model',
  modelsTitle: 'The GEEM AI model',
  modelsDescription: 'Built on multiple underlying models. Development continues.',
  platformLabel: 'The GEEM platform',
  platformTitle: 'One connected AI platform',
  platformDescription: 'Connecting AI capabilities to your workspace and business context.',
  controls: ['Workspace knowledge', 'Access and usage controls', 'Connected tools'],
  outputs: [
    { id: 'general', title: 'General AI', description: 'Explore ideas, write and understand information.' },
    { id: 'experts', title: 'Business Experts', description: 'Put your business knowledge to work through Experts across your channels.' },
    { id: 'actions', title: 'Connected actions', description: 'Look up information or request a permitted system action.' },
  ],
  note: 'Our platform brings the GEEM model, workspace knowledge and connected tools into one experience.',
  valuesLabel: 'What this means for your business',
  values: [
    'Start everyday AI work in a shared, familiar workspace.',
    'Give each Expert the knowledge and purpose your team needs.',
    'Keep system access and action approvals in your connected workflow.',
    'Reuse knowledge and integrations, and match capacity to usage to help reduce adoption costs.',
  ],
};

const ar: PlatformFoundationCopy = {
  eyebrow: 'التقنية وراء GEEM',
  title: 'نموذج نطوّره وبنية تحتية نمتلكها',
  description:
    'نموذج GEEM خضع للضبط الدقيق بالاعتماد على عدة نماذج أساسية. نشغّل نماذج مفتوحة المصدر بأوزان مختلفة على وحدات GPU وخوادم نمتلكها، ونواصل تطوير GEEM لتلبية احتياجات الأعمال.',
  infrastructureLabel: 'التشغيل والبنية التحتية',
  infrastructureTitle: 'سحابة GEEM أو مقر مؤسستك',
  infrastructureDescription:
    'استخدم سحابة GEEM أو بنية مخصصة نوفّرها في موقعك، مع تخطيط سعة GPU والتخزين والشبكات وفق حجم العمل.',
  diagramLabel: 'كيف يدعم نموذج GEEM قدرات المنصة',
  modelsLabel: 'نموذج نطوّره باستمرار',
  modelsTitle: 'نموذج GEEM للذكاء الاصطناعي',
  modelsDescription: 'نطوّره بالاعتماد على عدة نماذج أساسية.',
  platformLabel: 'منصة GEEM',
  platformTitle: 'منصة واحدة لقدرات GEEM',
  platformDescription: 'تربط قدرات الذكاء الاصطناعي بمساحة عملك ومعرفة مؤسستك.',
  controls: ['معرفة مؤسستك', 'إدارة الصلاحيات والاستخدام', 'الأدوات المتصلة'],
  outputs: [
    { id: 'general', title: 'مساعدة عامة', description: 'طوّر أفكارك، وصغ محتواك، وافهم المعلومات.' },
    { id: 'experts', title: 'خبراء الأعمال', description: 'وظّف معرفة مؤسستك عبر خبراء يخدمون قنواتك المختلفة.' },
    { id: 'actions', title: 'إجراءات عبر أنظمتك', description: 'استعلم عن بيانات أنظمتك أو اطلب تنفيذ إجراء تسمح به صلاحياتك.' },
  ],
  note: 'تجمع منصتنا نموذج GEEM ومعرفة مؤسستك وأدواتها المتصلة في تجربة واحدة.',
  valuesLabel: 'الفائدة لمؤسستك',
  values: [
    'أنجز مهامك اليومية بمساعدة الذكاء الاصطناعي في مساحة عمل مشتركة.',
    'حدّد مهمة كل خبير وزوّده بالمعرفة التي يحتاجها فريقك.',
    'حافظ على صلاحيات الأنظمة والموافقات المطلوبة عند ربط إجراءات العمل.',
    'أعد استخدام المعرفة والتكاملات، وخطّط السعة بحسب الاستخدام للمساعدة على خفض كلفة التبنّي.',
  ],
};

export function getPlatformFoundationCopy(locale: Locale): PlatformFoundationCopy {
  return locale === 'en' ? en : ar;
}
