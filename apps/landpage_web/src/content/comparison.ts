import type { Locale } from '../lib/i18n';

type ComparisonSource = { label: string; href: string };

export type ComparisonPlatform = {
  id: string;
  name: string;
  category: string;
  offering: string;
  deployment: string;
  evaluation: string;
  sources: ComparisonSource[];
};

export type ComparisonCopy = {
  meta: { title: string; description: string };
  hero: { eyebrow: string; title: string; description: string; primary: string; secondary: string };
  updated: string;
  guide: { label: string; items: { title: string; description: string }[] };
  landscape: { eyebrow: string; title: string; description: string };
  labels: { offering: string; deployment: string; evaluation: string; sources: string; geem: string };
  platforms: ComparisonPlatform[];
  costs: { eyebrow: string; title: string; description: string; items: { title: string; description: string }[]; conclusion: string };
  cta: { eyebrow: string; title: string; description: string; primary: string; secondary: string };
};

const sources = {
  microsoft: [
    { label: 'Architecture', href: 'https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/architecture-overview' },
    { label: 'Private networking', href: 'https://learn.microsoft.com/en-us/microsoft-copilot-studio/admin-network-isolation-vnet' },
  ],
  google: [
    { label: 'Agent Runtime', href: 'https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime' },
    { label: 'ADK deployment', href: 'https://adk.dev/deploy/' },
    { label: 'Distributed Cloud', href: 'https://cloud.google.com/distributed-cloud' },
  ],
  openai: [{ label: 'Frontier', href: 'https://openai.com/index/introducing-openai-frontier/' }],
  humain: [
    { label: 'IQ', href: 'https://www.humain.com/iq' },
    { label: 'ONE', href: 'https://www.humain.com/one' },
    { label: 'Compute', href: 'https://www.humain.com/en/compute.html' },
  ],
};

const en: ComparisonCopy = {
  meta: {
    title: 'Compare enterprise AI platforms and deployment options | GEEM',
    description: 'Compare GEEM, Microsoft Copilot Studio, Google, OpenAI Frontier and HUMAIN by deployment, business integration and practical evaluation criteria.',
  },
  hero: {
    eyebrow: 'Platform comparison',
    title: 'Choose AI around the way your business works',
    description: 'Compare where AI runs, how it connects to your work and what your team will need to operate it. Start with your requirements, then assess the platform.',
    primary: 'Discuss your requirements',
    secondary: 'Explore the comparison',
  },
  updated: 'Updated 10 September 2026',
  guide: {
    label: 'Three questions to guide your decision',
    items: [
      { title: 'Where will it run?', description: 'Cloud, your premises and the infrastructure each option requires' },
      { title: 'What will it connect?', description: 'Business knowledge, channels, systems and authorized actions' },
      { title: 'What will it take to operate?', description: 'Setup, usage, internal effort and ongoing support' },
    ],
  },
  landscape: {
    eyebrow: 'The platform landscape',
    title: 'Different platforms, different routes to deployment',
    description: 'Read each platform’s deployment scope alongside its capabilities. Managed services, portable agents and on-site infrastructure can be separate offerings.',
  },
  labels: { offering: 'Core offering', deployment: 'Deployment approach', evaluation: 'What to evaluate', sources: 'Official sources', geem: 'Our platform' },
  platforms: [
    {
      id: 'geem', name: 'GEEM', category: 'Arabic AI, Experts and business integration',
      offering: 'A fine-tuned GEEM model built on multiple underlying models, with knowledge-fed Experts, channels, authorized actions and OCR/HTR. Model development continues on GEEM-owned GPUs and servers using open-source models with different weights.',
      deployment: 'Run on GEEM cloud or on your premises. GEEM can supply on-site infrastructure sized for your workloads and operating requirements.',
      evaluation: 'Working embedded integrations include DALSEEN ERP, DALSEEN Platform and Qaf Noon. Assess your Arabic content, required systems, permissions and deployment scope with the team.',
      sources: [{ label: 'GEEM capabilities', href: '/en#platform' }, { label: 'Client Agent API', href: '/en/agent-ai' }],
    },
    {
      id: 'microsoft', name: 'Microsoft Copilot Studio', category: 'Managed enterprise agent platform',
      offering: 'Build and govern agents that use organizational knowledge, business tools and workflows within the Microsoft ecosystem and connected services.',
      deployment: 'Managed SaaS with private-network connections to business systems. Connecting to an on-site system is distinct from hosting the Copilot Studio runtime on your premises.',
      evaluation: 'Review your Microsoft environment, supported connections, agent governance and the configuration needed for private resources.',
      sources: sources.microsoft,
    },
    {
      id: 'google', name: 'Google Gemini Enterprise Agent Platform', category: 'Managed agents and a broader deployment ecosystem',
      offering: 'A managed agent runtime with development tools, including the portable Agent Development Kit (ADK). Google Distributed Cloud is a separate on-site offering.',
      deployment: 'Agent Runtime is managed on Google Cloud. ADK agents can run in other container environments; Distributed Cloud provides separate on-site infrastructure and AI capabilities.',
      evaluation: 'Specify which runtime, models and services you need. Availability in Distributed Cloud does not mean every managed platform service is available on site.',
      sources: sources.google,
    },
    {
      id: 'openai', name: 'OpenAI Frontier', category: 'Enterprise agent platform',
      offering: 'An enterprise platform for agents with shared business context, permissions and tools to manage their work.',
      deployment: 'Agent execution can span local environments, enterprise cloud and OpenAI-hosted runtimes. Local agent execution does not mean self-hosting proprietary OpenAI model weights.',
      evaluation: 'Separate where the agent executes from where model inference runs. Review the business systems, data access and operating controls your workflow requires.',
      sources: sources.openai,
    },
    {
      id: 'humain', name: 'HUMAIN IQ / ONE + Compute', category: 'Arabic AI, enterprise agents and infrastructure',
      offering: 'IQ offers Arabic-focused AI capabilities; ONE supports enterprise agents and business integration. Compute provides the underlying infrastructure options.',
      deployment: 'Cloud and customer environments, with on-site or edge AI through Compute and AI in a Box. Deployment scope depends on the selected offering.',
      evaluation: 'Assess the combination of IQ, ONE and Compute for your Arabic workloads, business applications, hardware needs and operating responsibilities.',
      sources: sources.humain,
    },
  ],
  costs: {
    eyebrow: 'A practical cost comparison',
    title: 'Compare the whole operating model',
    description: 'Use the same workflows and expected demand when evaluating each option. Reusing knowledge and integrations can reduce repeated work; total cost depends on the deployment.',
    items: [
      { title: 'Define the workload', description: 'Compare expected users, requests, document volumes, response needs and peak demand.' },
      { title: 'Include setup and integration', description: 'Account for preparing knowledge, connecting systems, configuring permissions and testing real workflows.' },
      { title: 'Plan infrastructure and usage', description: 'Review service and model usage charges alongside hardware, capacity, networking, maintenance and support where applicable.' },
      { title: 'Measure ongoing effort', description: 'Include team training, quality review, model updates, monitoring and the effort to extend the first use case.' },
    ],
    conclusion: 'A focused evaluation should establish useful output, reliable authorized actions and a realistic operating cost before wider rollout.',
  },
  cta: {
    eyebrow: 'Evaluate GEEM for your organization',
    title: 'Start with a workflow and a deployment plan',
    description: 'Bring your language needs, business systems and infrastructure requirements. We can scope a GEEM cloud or on-site approach and identify what to validate together.',
    primary: 'Talk to the GEEM team',
    secondary: 'Explore business use cases',
  },
};

const ar: ComparisonCopy = {
  meta: {
    title: 'مقارنة منصات الذكاء الاصطناعي وخيارات التشغيل | GEEM',
    description: 'قارن GEEM وMicrosoft Copilot Studio وGoogle وOpenAI Frontier وHUMAIN من حيث التشغيل والتكامل ومعايير التقييم المناسبة لمؤسستك.',
  },
  hero: {
    eyebrow: 'مقارنة المنصات',
    title: 'اختر الذكاء الاصطناعي الذي يناسب أعمالك',
    description: 'قارن بيئة التشغيل، والربط بأنظمة العمل، والموارد التي يحتاجها فريقك لإدارة الحل. حدّد متطلباتك أولًا، ثم قيّم المنصة على أساسها.',
    primary: 'ناقش متطلباتك معنا',
    secondary: 'استعرض المقارنة',
  },
  updated: 'آخر تحديث: 10 سبتمبر 2026',
  guide: {
    label: 'ثلاثة أسئلة تساعدك على الاختيار',
    items: [
      { title: 'أين سيعمل الحل؟', description: 'على السحابة أو داخل منشأتك، والبنية اللازمة لكل خيار' },
      { title: 'بماذا سيرتبط؟', description: 'معرفة المؤسسة وقنواتها وأنظمتها والإجراءات المصرّح بها' },
      { title: 'ما متطلبات تشغيله؟', description: 'الإعداد والاستخدام وجهد الفريق والدعم المستمر' },
    ],
  },
  landscape: {
    eyebrow: 'المنصات وخياراتها',
    title: 'خيارات متعددة لتطبيق الذكاء الاصطناعي',
    description: 'قيّم قدرات كل منصة ونطاق تشغيلها. فقد تكون الخدمات المُدارة، والوكلاء القابلون للتشغيل في بيئات مختلفة، والبنية المحلية عروضًا مستقلة.',
  },
  labels: { offering: 'ما تقدّمه المنصة', deployment: 'خيارات التشغيل', evaluation: 'ما ينبغي تقييمه', sources: 'المصادر الرسمية', geem: 'منصتنا' },
  platforms: [
    {
      id: 'geem', name: 'GEEM', category: 'ذكاء يدعم العربية وخبراء مرتبطون بأعمالك',
      offering: 'نموذج GEEM مطوّر بالضبط الدقيق اعتمادًا على عدة نماذج أساسية، مع خبراء يستفيدون من معرفة المؤسسة وقنوات وإجراءات مصرّح بها وقدرات OCR/HTR. نواصل تطوير النموذج وتشغيل نماذج مفتوحة المصدر بأوزان مختلفة على وحدات GPU وخوادم نملكها.',
      deployment: 'يعمل على سحابة GEEM أو داخل منشأتك. ويمكننا توفير بنية محلية تتناسب مع أحمال العمل ومتطلبات التشغيل لديك.',
      evaluation: 'GEEM مدمج ويعمل حاليًا في DALSEEN ERP وDALSEEN Platform وQaf Noon. قيّم معنا محتواك العربي والأنظمة المطلوبة والصلاحيات ونطاق التشغيل.',
      sources: [{ label: 'قدرات GEEM', href: '/ar#platform' }, { label: 'Client Agent API', href: '/ar/agent-ai' }],
    },
    {
      id: 'microsoft', name: 'Microsoft Copilot Studio', category: 'منصة مُدارة لوكلاء المؤسسات',
      offering: 'بناء الوكلاء وإدارتهم بالاستفادة من معرفة المؤسسة وأدواتها وإجراءات العمل ضمن منظومة Microsoft والخدمات المتصلة بها.',
      deployment: 'منصة سحابية مُدارة تتيح الاتصال بأنظمة الأعمال عبر الشبكات الخاصة. الربط بنظام داخل المنشأة يختلف عن استضافة منصة Copilot Studio نفسها محليًا.',
      evaluation: 'راجع بيئة Microsoft لديك، والاتصالات المدعومة، وضوابط إدارة الوكلاء، والإعدادات المطلوبة للوصول إلى الموارد الخاصة.',
      sources: [{ label: 'بنية المنصة', href: sources.microsoft[0].href }, { label: 'الشبكات الخاصة', href: sources.microsoft[1].href }],
    },
    {
      id: 'google', name: 'Google Gemini Enterprise Agent Platform', category: 'بيئات مُدارة للوكلاء وخيارات تشغيل أوسع',
      offering: 'بيئة مُدارة لتشغيل الوكلاء وأدوات تطوير تشمل Agent Development Kit (ADK) لبناء وكلاء يمكن تشغيلهم في بيئات مختلفة. أما Google Distributed Cloud فهو عرض مستقل للتشغيل داخل المنشأة.',
      deployment: 'تعمل Agent Runtime على سحابة Google. ويمكن تشغيل وكلاء ADK في بيئات حاويات أخرى، بينما يوفّر Distributed Cloud بنية وقدرات ذكاء اصطناعي محلية بصورة مستقلة.',
      evaluation: 'حدّد بيئة التشغيل والنماذج والخدمات المطلوبة. إتاحة قدرة ضمن Distributed Cloud لا تعني إتاحة جميع خدمات المنصة المُدارة محليًا.',
      sources: [{ label: 'Agent Runtime', href: sources.google[0].href }, { label: 'تشغيل ADK', href: sources.google[1].href }, { label: 'Distributed Cloud', href: sources.google[2].href }],
    },
    {
      id: 'openai', name: 'OpenAI Frontier', category: 'منصة لوكلاء المؤسسات',
      offering: 'منصة مؤسسية للوكلاء تجمع سياق الأعمال المشترك والصلاحيات والأدوات اللازمة لإدارة مهام الوكلاء.',
      deployment: 'يمكن تنفيذ الوكلاء في بيئات محلية أو على سحابة المؤسسة أو ضمن بيئات تستضيفها OpenAI. تنفيذ الوكيل محليًا لا يعني استضافة أوزان نماذج OpenAI الخاصة داخل المنشأة.',
      evaluation: 'ميّز بين مكان تنفيذ الوكيل ومكان تشغيل النموذج. راجع أنظمة العمل وصلاحيات الوصول إلى البيانات وضوابط التشغيل التي يحتاجها الاستخدام.',
      sources: sources.openai,
    },
    {
      id: 'humain', name: 'HUMAIN IQ / ONE + Compute', category: 'ذكاء يدعم العربية ووكلاء وبنية للمؤسسات',
      offering: 'يقدّم IQ قدرات ذكاء اصطناعي تركز على العربية، ويدعم ONE وكلاء المؤسسات والتكامل مع أنظمة العمل. ويوفّر Compute خيارات البنية اللازمة للتشغيل.',
      deployment: 'خيارات سحابية وبيئات خاصة بالعميل، مع تشغيل محلي أو طرفي عبر Compute وAI in a Box. ويتحدد نطاق التشغيل بحسب العرض المختار.',
      evaluation: 'قيّم الجمع بين IQ وONE وCompute وفق استخداماتك بالعربية وتطبيقات الأعمال واحتياجات الأجهزة وتوزيع مسؤوليات التشغيل.',
      sources: sources.humain,
    },
  ],
  costs: {
    eyebrow: 'مقارنة عملية للتكلفة',
    title: 'احسب تكلفة التشغيل كاملة',
    description: 'قارن الخيارات باستخدام إجراءات العمل نفسها وحجم الطلب المتوقع. تساعد إعادة استخدام المعرفة والتكاملات على تقليل العمل المتكرر، وتتحدد التكلفة الإجمالية وفق طريقة التشغيل.',
    items: [
      { title: 'حدّد حجم الاستخدام', description: 'قارن عدد المستخدمين والطلبات وحجم المستندات وسرعة الاستجابة المطلوبة والطلب في أوقات الذروة.' },
      { title: 'احسب الإعداد والتكامل', description: 'أدرج تجهيز المعرفة وربط الأنظمة وضبط الصلاحيات واختبار إجراءات العمل الفعلية.' },
      { title: 'خطّط للبنية والاستهلاك', description: 'راجع رسوم الخدمات واستخدام النماذج، وتكاليف الأجهزة والسعة والشبكات والصيانة والدعم عند الحاجة.' },
      { title: 'قدّر الجهد المستمر', description: 'احسب تدريب الفريق ومراجعة الجودة وتحديث النماذج والمراقبة والجهد اللازم لتوسيع نطاق الاستخدام.' },
    ],
    conclusion: 'تحقّق من جودة المخرجات وموثوقية الإجراءات المصرّح بها والتكلفة التشغيلية الواقعية في تقييم محدد قبل التوسّع.',
  },
  cta: {
    eyebrow: 'قيّم GEEM لمؤسستك',
    title: 'ابدأ باستخدام واضح وخطة تشغيل',
    description: 'شاركنا احتياجاتك اللغوية وأنظمة أعمالك ومتطلبات البنية. نحدّد معك نهجًا سحابيًا أو محليًا لتشغيل GEEM، وما يلزم التحقق منه قبل الإطلاق.',
    primary: 'تواصل مع فريق GEEM',
    secondary: 'استكشف استخدامات الأعمال',
  },
};

export function getComparisonCopy(locale: Locale): ComparisonCopy {
  return locale === 'ar' ? ar : en;
}
