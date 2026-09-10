import type { Locale } from '../lib/i18n';

const en = {
  eyebrow: 'Cloud & on-site',
  title: 'Your AI, in the environment your business needs',
  description: 'Choose GEEM cloud or run GEEM at your premises. We help you align infrastructure, integrations and capacity with the way your organization works.',
  options: [
    {
      id: 'cloud',
      label: 'GEEM cloud',
      title: 'Start without an on-site GPU setup',
      description: 'Use GEEM on our cloud infrastructure and connect the knowledge, channels and systems your teams need.',
      points: ['No need to provision GPUs at your premises', 'Plan service capacity around your expected usage'],
    },
    {
      id: 'on-site',
      label: 'At your premises',
      title: 'Bring GEEM closer to your operations',
      description: 'Run GEEM within your organization. We can provide the on-site infrastructure, configured around your workloads and operating requirements.',
      points: ['GPU, storage and network sizing for your needs', 'Deployment scope agreed with your technical team'],
    },
  ],
  costTitle: 'Make adoption costs easier to manage',
  costDescription: 'Match capacity to demand, reuse Experts and integrations, and expand from workflows that deliver useful results. These choices can reduce duplicated setup and unnecessary infrastructure spending.',
  planningTitle: 'What we plan with your team',
  planningItems: [
    { title: 'Workload & capacity', text: 'Users, models, document volumes and expected demand.' },
    { title: 'Data & connections', text: 'Data location, approved systems and any external services.' },
    { title: 'Operations & cost', text: 'Hardware, service capacity, maintenance and the expansion plan.' },
  ],
  contactCta: 'Plan your deployment',
  compareCta: 'Compare AI platforms',
};

const ar: typeof en = {
  eyebrow: 'السحابة والتشغيل داخل المنشأة',
  title: 'ذكاء اصطناعي في بيئة تناسب أعمالك',
  description: 'اختر سحابة GEEM أو شغّل GEEM داخل منشأتك. نساعدك على مواءمة البنية التحتية والتكاملات والقدرة التشغيلية مع متطلبات عملك.',
  options: [
    {
      id: 'cloud',
      label: 'سحابة GEEM',
      title: 'ابدأ دون تجهيز وحدات GPU داخل منشأتك',
      description: 'استخدم GEEM على بنيتنا السحابية، واربطه بالمعرفة والقنوات والأنظمة التي تحتاج إليها فرقك.',
      points: ['دون الحاجة إلى تجهيز وحدات GPU داخل المنشأة', 'قدرة تشغيلية تتناسب مع الاستخدام المتوقع'],
    },
    {
      id: 'on-site',
      label: 'داخل منشأتك',
      title: 'GEEM أقرب إلى بيئة عملك',
      description: 'شغّل GEEM داخل منشأتك. ويمكننا توفير البنية التحتية اللازمة وتجهيزها وفق أحمال العمل والمتطلبات التشغيلية.',
      points: ['تحديد احتياجات GPU والتخزين والشبكة', 'نطاق تشغيل يُحدّد بالتنسيق مع فريقك التقني'],
    },
  ],
  costTitle: 'تحكّم أفضل في تكلفة تبنّي الذكاء الاصطناعي',
  costDescription: 'واءم القدرة التشغيلية مع حجم الطلب، وأعد استخدام الخبراء والتكاملات، وتوسّع انطلاقًا من مسارات العمل التي تحقق قيمة ملموسة. تساعد هذه الخيارات على تقليل تكرار الإعداد والإنفاق غير الضروري على البنية التحتية.',
  planningTitle: 'ما الذي نخطّط له مع فريقك',
  planningItems: [
    { title: 'أحمال العمل والقدرة التشغيلية', text: 'عدد المستخدمين والنماذج وحجم المستندات والطلب المتوقع.' },
    { title: 'البيانات والتكاملات', text: 'موقع البيانات والأنظمة المعتمدة وأي خدمات خارجية متصلة.' },
    { title: 'التشغيل والتكلفة', text: 'الأجهزة والقدرة التشغيلية والصيانة وخطة التوسّع.' },
  ],
  contactCta: 'خطّط لتشغيل GEEM في منشأتك',
  compareCta: 'قارن منصات الذكاء الاصطناعي',
};

export function getDeploymentCopy(locale: Locale) {
  return locale === 'ar' ? ar : en;
}
