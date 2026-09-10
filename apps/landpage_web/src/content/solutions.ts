import type { Locale } from '../lib/i18n';
import type { UseCaseId } from './use-cases';

export type SectorId =
  | 'government'
  | 'tourism'
  | 'research'
  | 'retail'
  | 'industry'
  | 'facilities'
  | 'education'
  | 'professional';

type SectorApplication = {
  title: string;
  description: string;
  proposed?: true;
};

type SolutionFoundation = {
  title: string;
  description: string;
};

export type Sector = {
  id: SectorId;
  label: string;
  audience: string;
  title: string;
  description: string;
  challenge: string;
  outcome: string;
  imageAlt: string;
  applications: [SectorApplication, SectorApplication, SectorApplication, SectorApplication];
  useCaseIds: UseCaseId[];
};

export type SolutionsCopy = {
  eyebrow: string;
  title: string;
  description: string;
  viewsLabel: string;
  sectorView: string;
  useCaseView: string;
  sectorsLabel: string;
  audienceLabel: string;
  applicationsLabel: string;
  challengeLabel: string;
  outcomeLabel: string;
  relatedLabel: string;
  foundationsLabel: string;
  foundations: [SolutionFoundation, SolutionFoundation, SolutionFoundation];
  proposedLabel: string;
  illustrationLabel: string;
  ctaLabel: string;
  note: string;
  sectors: Sector[];
};

const en: SolutionsCopy = {
  eyebrow: 'Solutions for your work',
  title: 'GEEM for your organization',
  description:
    'Connect your organization’s knowledge, systems and devices through specialized AI Experts. Start with a specific business need, bring GEEM into your existing channels, and reuse knowledge and integrations as you expand.',
  viewsLabel: 'Explore solutions by sector or use case',
  sectorView: 'By sector',
  useCaseView: 'By use case',
  sectorsLabel: 'Choose your sector',
  audienceLabel: 'Who it serves',
  applicationsLabel: 'Ways to apply GEEM',
  challengeLabel: 'The challenge',
  outcomeLabel: 'Expected value',
  relatedLabel: 'Related workflows',
  foundationsLabel: 'A common foundation for every sector',
  foundations: [
    {
      title: 'Arabic in your work context',
      description:
        'Support Arabic writing and explanations with your organization’s terminology and reference material, while reviewing varied phrasing and nuanced meanings in the context of your work.',
    },
    {
      title: 'Reuse the setup as you grow',
      description:
        'Reuse knowledge and validated integrations in suitable new workflows, with permissions for each team, to limit duplicated setup and help lower adoption effort and cost.',
    },
    {
      title: 'GEEM’s model and infrastructure',
      description:
        'GEEM’s fine-tuned AI is built on multiple underlying models. We run open-source models with different weights on our own GPUs and servers, with continued model development.',
    },
  ],
  proposedLabel: 'Proposed application',
  illustrationLabel: 'Illustrative setting',
  ctaLabel: 'Discuss your organization’s needs',
  note:
    'Examples are illustrative; connected actions require configured integrations, permission checks and human review where appropriate. Your application or connected service executes authorized actions, while official decisions remain with the responsible authority.',
  sectors: [
    {
      id: 'government',
      label: 'Government & municipalities',
      audience: 'Public authorities · Municipalities · Service centres',
      title: 'Support public services and regulatory coordination',
      description:
        'A service request may cross several teams before reaching its owner. GEEM brings service guidance and request context together so residents can prepare the next step and staff can follow the authority’s procedures.',
      challenge: 'Residents and staff navigate scattered service requirements, multiple channels and handoffs between responsible teams.',
      outcome: 'Clearer requests and shared context can help teams coordinate follow-up while retaining official decision authority.',
      imageAlt: 'A resident and municipal worker reviewing a tablet in a city street',
      applications: [
        {
          title: 'Guide residents',
          description: 'Explain service requirements and help residents identify the responsible authority and official channel.',
        },
        {
          title: 'Prepare and follow requests',
          description: 'Gather the required details, submit through an authorized integration and show the status returned by the system.',
        },
        {
          title: 'Flag potential compliance risks',
          description: 'Evaluate whether device or camera signals indicate potential violations, with supporting evidence for specialist review.',
          proposed: true,
        },
        {
          title: 'Route regulatory cases',
          description: 'Prepare a case summary and evidence for human review, then hand it to the responsible team through configured channels.',
        },
      ],
      useCaseIds: ['municipal', 'devices', 'employee'],
    },
    {
      id: 'tourism',
      label: 'Tourism & hospitality',
      audience: 'Hotels · Destinations · Visitor centres',
      title: 'Help visitors plan, explore and get assistance',
      description:
        'Visitor questions change with the destination, season and service. GEEM helps guests find relevant options, connects requests to hospitality systems and gives service teams a shared reference for their daily work.',
      challenge: 'Changing schedules, seasonal demand and language differences make consistent visitor information difficult to maintain across channels.',
      outcome: 'Visitors can find relevant guidance while hospitality teams share current information and coordinate guest requests.',
      imageAlt: 'A guide assisting a visitor at a destination information centre',
      applications: [
        {
          title: 'Guide each visit',
          description: 'Present suitable activities, opening times and site guidelines using current information from the destination.',
        },
        {
          title: 'Support guest requests',
          description: 'Explain service options, route requests through connected hotel or destination systems and return their status.',
        },
        {
          title: 'Equip service teams',
          description: 'Help staff find operating procedures and service instructions during guest interactions and routine work.',
        },
        {
          title: 'Prepare seasonal content',
          description: 'Draft Arabic and English updates for seasonal events and visitor FAQs, for staff review before publication.',
        },
      ],
      useCaseIds: ['visitor', 'customer', 'employee'],
    },
    {
      id: 'research',
      label: 'Research, archives & museums',
      audience: 'Research centres · Archives · Museums',
      title: 'Make collections searchable',
      description:
        'Printed records and handwritten material hold knowledge that can be hard to retrieve. GEEM uses OCR and HTR to prepare text for specialist review, then helps organize it for research and museum guidance.',
      challenge: 'Scanned pages and handwritten records need transcription, source checks and access rules before teams can reuse them.',
      outcome: 'Reviewed, searchable collections can support research and make selected heritage knowledge more accessible to visitors.',
      imageAlt: 'Researchers digitizing historical records with a document scanner',
      applications: [
        {
          title: 'Extract printed text',
          description: 'Use OCR to extract text from scanned documents for a researcher or curator to review.',
        },
        {
          title: 'Transcribe handwriting',
          description: 'Use HTR to prepare transcriptions that specialists check and correct against the original document.',
        },
        {
          title: 'Organize reviewed collections',
          description: 'Group validated text with its sources and make it available to research Experts under the collection’s access rules.',
        },
        {
          title: 'Explain exhibits to visitors',
          description: 'Answer visitor questions using museum-approved descriptions and public collection material, with references to the source.',
        },
      ],
      useCaseIds: ['research', 'arabic', 'visitor'],
    },
    {
      id: 'retail',
      label: 'Retail & e-commerce',
      audience: 'Retailers · Online stores · Retail groups',
      title: 'Guide shoppers from product choice to after-sales service',
      description:
        'Customers need product answers and order updates without repeating their request to each team. GEEM connects catalogue knowledge, service policies and permitted order data across your website, WhatsApp and business systems.',
      challenge: 'Catalogues, service policies and order updates often reach customers through different channels and teams.',
      outcome: 'Customers can get consistent product answers and clearer follow-up, while teams prepare catalogue content for review.',
      imageAlt: 'A shop owner working at a laptop in a retail store',
      applications: [
        {
          title: 'Explain product choices',
          description: 'Use confirmed catalogue details and specifications to help customers compare products against their needs.',
        },
        {
          title: 'Follow orders',
          description: 'Retrieve permitted order information and explain the status returned by your system.',
        },
        {
          title: 'Guide delivery and returns',
          description: 'Explain the policy and prepare eligible requests through your configured approval process.',
        },
        {
          title: 'Prepare catalogue updates',
          description: 'Draft product descriptions, FAQs and content changes from confirmed product information for your team to review and publish.',
        },
      ],
      useCaseIds: ['customer', 'sales', 'arabic'],
    },
    {
      id: 'industry',
      label: 'Industry & logistics',
      audience: 'Manufacturers · Warehouses · Logistics providers',
      title: 'Connect procedures, shipments and device signals',
      description:
        'Procedures, shipment updates and device signals often sit apart from the teams handling an exception. GEEM brings that context into the workflow and helps staff prepare follow-up and handovers using their operating instructions.',
      challenge: 'Teams must reconcile procedures, shipment exceptions and device readings while preserving context between shifts and sites.',
      outcome: 'Shared operational context can support more informed follow-up and clearer handovers between shifts, sites and teams.',
      imageAlt: 'Warehouse colleagues in hard hats and safety vests reviewing a tablet',
      applications: [
        {
          title: 'Find the relevant procedure',
          description: 'Retrieve approved operating and safety instructions through an Expert configured for the team’s role.',
        },
        {
          title: 'Investigate shipment exceptions',
          description: 'Retrieve the latest permitted shipment status and connect it with the applicable operating procedure.',
        },
        {
          title: 'Connect device signals',
          description: 'Integrate IoT devices and cameras, then relate available readings or observations to operational context.',
        },
        {
          title: 'Prepare shift handovers',
          description: 'Summarize incidents, actions taken and open tasks from available records for the outgoing team to check and hand over.',
        },
      ],
      useCaseIds: ['operations', 'devices', 'employee'],
    },
    {
      id: 'facilities',
      label: 'Real estate & facilities',
      audience: 'Property operators · Facilities teams · Business parks',
      title: 'Turn building issues into coordinated maintenance',
      description:
        'A maintenance report is easier to assess when teams can find the building context and service history. GEEM helps occupants prepare requests and gives facilities staff relevant procedures, manuals and permitted operating information.',
      challenge: 'Occupant reports, building manuals and maintenance updates are often spread across separate teams and systems.',
      outcome: 'More complete requests and accessible building knowledge can help facilities teams coordinate review and maintenance follow-up.',
      imageAlt: 'A facilities manager and maintenance engineer reviewing building information on a tablet',
      applications: [
        {
          title: 'Guide occupants',
          description: 'Explain property services and procedures using the operator’s information for residents, tenants and other occupants.',
        },
        {
          title: 'Prepare maintenance requests',
          description: 'Gather the location and issue details, then route a request to the connected maintenance system for review.',
        },
        {
          title: 'Support facilities follow-up',
          description: 'Bring permitted device readings and case updates together to help staff assess the next action.',
        },
        {
          title: 'Find building manuals',
          description: 'Help technicians locate the relevant equipment manual, service procedure and building-specific guidance within their access rights.',
        },
      ],
      useCaseIds: ['devices', 'operations', 'it'],
    },
    {
      id: 'education',
      label: 'Education & training',
      audience: 'Schools · Universities · Training providers',
      title: 'Support teaching and campus work',
      description:
        'Learners, educators and administrative teams need different guidance from the same institution. GEEM helps them find programme information, prepare teaching material and navigate staff procedures through Experts with defined sources and roles.',
      challenge: 'Learners and employees navigate different resources and procedures, while educators repeatedly prepare explanations and materials.',
      outcome: 'Relevant guidance and reviewed drafts can support learning, staff induction and more complete administrative requests.',
      imageAlt: 'A lecturer helping an adult student at a laptop in a university learning-resource centre',
      applications: [
        {
          title: 'Guide learners',
          description: 'Explain programme information, learning resources and student-service requirements from the institution’s materials.',
        },
        {
          title: 'Prepare learning material',
          description: 'Draft explanations, summaries and activities for an educator to review before use.',
        },
        {
          title: 'Support administrative requests',
          description: 'Help staff gather the required details and follow a request through existing approval processes.',
        },
        {
          title: 'Help new staff get started',
          description: 'Explain induction steps, responsibilities and administrative procedures using the institution’s staff handbook.',
        },
      ],
      useCaseIds: ['arabic', 'employee', 'research'],
    },
    {
      id: 'professional',
      label: 'Professional services',
      audience: 'Consultancies · Engineering firms · Business service providers',
      title: 'Turn project knowledge into proposals and client delivery',
      description:
        'Client briefs, project references and delivery updates are often dispersed across a firm. GEEM helps teams prepare proposals, retrieve relevant project knowledge and coordinate client work without starting every assignment from scratch.',
      challenge: 'Teams repeatedly assemble client requirements, project references and delivery updates from documents and business systems.',
      outcome: 'Reusable project knowledge can help teams prepare stronger drafts and coordinate onboarding and ongoing client requests.',
      imageAlt: 'Business colleagues discussing a project around a laptop',
      applications: [
        {
          title: 'Prepare proposal drafts',
          description: 'Combine a client brief with the firm’s service information for the team to review and send.',
        },
        {
          title: 'Use project knowledge',
          description: 'Summarize permitted project documents and help teams find relevant references for their assignment.',
        },
        {
          title: 'Coordinate client requests',
          description: 'Gather requirements and retrieve permitted updates from connected business systems.',
        },
        {
          title: 'Prepare client onboarding',
          description: 'Build onboarding checklists, gather required client information and summarize the agreed next steps for the team to confirm.',
        },
      ],
      useCaseIds: ['sales', 'developer', 'finance'],
    },
  ],
};

const ar: SolutionsCopy = {
  eyebrow: 'حلول تناسب طبيعة عملك',
  title: 'قدرات GEEM في خدمة مؤسستك',
  description:
    'اربط معرفة مؤسستك وأنظمتها وأجهزتها بخبراء متخصصين. ابدأ باحتياج محدد، وقدّم قدرات GEEM عبر قنواتك الحالية، ثم توسّع بالاستفادة من المعرفة والتكاملات التي أعددتها.',
  viewsLabel: 'استكشف الحلول حسب القطاع أو الاستخدام',
  sectorView: 'حسب القطاع',
  useCaseView: 'حسب الاستخدام',
  sectorsLabel: 'اختر قطاعك',
  audienceLabel: 'الجهات المستفيدة',
  applicationsLabel: 'تطبيقات GEEM في هذا القطاع',
  challengeLabel: 'التحدّي',
  outcomeLabel: 'الفائدة المستهدفة',
  relatedLabel: 'استخدامات ذات صلة',
  foundationsLabel: 'أساس مشترك يخدم مختلف القطاعات',
  foundations: [
    {
      title: 'العربية في سياق عملك',
      description:
        'استفد من مصطلحات مؤسستك ومراجعها في الكتابة والشرح بالعربية، مع مراجعة تنوّع الصياغة ودقة المعنى وفق طبيعة عملك.',
    },
    {
      title: 'إعداد تستفيد منه الفرق',
      description:
        'توسّع بالمعرفة والتكاملات التي تحققت منها، مع صلاحيات مستقلة لكل فريق، لتقليل الإعداد المتكرر وجهد تبنّي التقنية وكلفتها.',
    },
    {
      title: 'نموذج GEEM وبنيتنا الخاصة',
      description:
        'نموذج GEEM خاضع للضبط الدقيق ومبني على عدة نماذج أساسية. نشغّل نماذج مفتوحة المصدر بأوزان مختلفة على خوادمنا ومعالجاتنا الرسومية، مع مواصلة تطوير النموذج.',
    },
  ],
  proposedLabel: 'تطبيق مقترح',
  illustrationLabel: 'صورة توضيحية',
  ctaLabel: 'ناقش احتياجات مؤسستك',
  note:
    'الأمثلة توضيحية؛ وتتطلب الإجراءات المتصلة تكاملات مهيّأة والتحقق من الصلاحيات ومراجعة بشرية بحسب الإجراء. ينفّذ تطبيقك أو الخدمة المتصلة الإجراءات المصرّح بها، وتبقى القرارات الرسمية لدى الجهة المختصة.',
  sectors: [
    {
      id: 'government',
      label: 'الجهات الحكومية والبلديات',
      audience: 'الجهات الحكومية · البلديات · مراكز خدمة المستفيدين',
      title: 'دعم الخدمات الحكومية والتنسيق مع الجهات الرقابية',
      description:
        'قد يمر طلب الخدمة بعدة فرق قبل وصوله إلى المسؤول عنه. يجمع GEEM إرشادات الخدمة وتفاصيل الطلب ليساعد المستفيد على تجهيز الخطوة التالية ويمكّن الموظف من متابعتها وفق إجراءات الجهة.',
      challenge: 'يتنقل المستفيد والموظف بين متطلبات متفرقة وقنوات متعددة قبل وصول الطلب مكتملًا إلى الفريق المختص.',
      outcome: 'طلبات أوضح ومعلومات مشتركة تساعد الفرق على تنسيق المتابعة، مع بقاء القرار الرسمي للجهة المختصة.',
      imageAlt: 'مستفيد وموظف بلدي يراجعان جهازًا لوحيًا في أحد شوارع المدينة',
      applications: [
        {
          title: 'إرشاد المستفيدين',
          description: 'شرح متطلبات الخدمة ومساعدة المستفيد على تحديد الجهة المسؤولة والقناة الرسمية المناسبة.',
        },
        {
          title: 'تجهيز الطلبات ومتابعتها',
          description: 'جمع التفاصيل المطلوبة وإرسال الطلب عبر تكامل مصرّح به، ثم عرض الحالة الواردة من النظام.',
        },
        {
          title: 'رصد مخاطر المخالفات المحتملة',
          description: 'تقييم مؤشرات الأجهزة أو الكاميرات لاحتمال وقوع مخالفة، مع عرض الأدلة الداعمة لمراجعة المختصين.',
          proposed: true,
        },
        {
          title: 'إحالة الحالات الرقابية',
          description: 'إعداد ملخص الحالة وأدلتها للمراجعة البشرية، ثم إحالته إلى الفريق المختص عبر القنوات المهيّأة.',
        },
      ],
      useCaseIds: ['municipal', 'devices', 'employee'],
    },
    {
      id: 'tourism',
      label: 'السياحة والضيافة',
      audience: 'الفنادق · الوجهات السياحية · مراكز الزوار',
      title: 'مساعدة الزوار على التخطيط والاستكشاف وطلب الخدمة',
      description:
        'تختلف أسئلة الزوار باختلاف الوجهة والموسم والخدمة. يساعدهم GEEM على معرفة الخيارات المناسبة، ويربط طلباتهم بأنظمة الضيافة، ويوفّر لفرق الخدمة مرجعًا مشتركًا لعملهم اليومي.',
      challenge: 'تتغير المواعيد والمواسم ولغات الزوار، فيصعب الحفاظ على معلومات متسقة ومحدّثة عبر جميع قنوات الخدمة.',
      outcome: 'إرشاد يناسب الزائر ومعلومات مشتركة لفرق الضيافة تساعد على تنسيق الطلبات ومتابعتها عبر قنوات الخدمة.',
      imageAlt: 'مرشد يساعد زائرًا في مركز معلومات سياحي',
      applications: [
        {
          title: 'إرشاد لكل زيارة',
          description: 'عرض الأنشطة المناسبة وأوقات العمل وإرشادات المواقع من معلومات الوجهة المحدّثة.',
        },
        {
          title: 'متابعة طلبات الضيوف',
          description: 'شرح خيارات الخدمة وتوجيه الطلبات عبر أنظمة الفندق أو الوجهة المتصلة وعرض حالتها.',
        },
        {
          title: 'مساندة فرق الخدمة',
          description: 'مساعدة الموظفين على الوصول إلى إجراءات التشغيل وتعليمات الخدمة أثناء التعامل مع الضيوف والعمل اليومي.',
        },
        {
          title: 'محتوى موسمي بلغتين',
          description: 'صياغة تحديثات الفعاليات الموسمية وإجابات الأسئلة الشائعة بالعربية والإنجليزية ليراجعها الفريق قبل اعتمادها.',
        },
      ],
      useCaseIds: ['visitor', 'customer', 'employee'],
    },
    {
      id: 'research',
      label: 'مراكز الأبحاث والأرشيف والمتاحف',
      audience: 'مراكز الأبحاث · الأرشيفات · المتاحف',
      title: 'مجموعات معرفية قابلة للبحث',
      description:
        'تختزن الوثائق المطبوعة والمكتوبة بخط اليد معرفة يصعب استرجاعها. يستخدم GEEM قدرات OCR وHTR لإعداد النصوص لمراجعة المختص، ثم يساعد في تنظيمها لخدمة البحث والمعلومات المتحفية.',
      challenge: 'تحتاج الوثائق الممسوحة والمكتوبة بخط اليد إلى استخراج النص والتحقق من المصدر وضبط الوصول قبل استخدامها.',
      outcome: 'مجموعات مراجَعة وقابلة للبحث تدعم الباحثين وتتيح تقديم المعرفة التراثية المختارة للزوار وفق ضوابط المؤسسة.',
      imageAlt: 'باحثان يعملان على رقمنة سجلات تاريخية باستخدام ماسح ضوئي للوثائق',
      applications: [
        {
          title: 'استخراج النصوص المطبوعة',
          description: 'استخدام OCR لاستخراج النص من الوثائق الممسوحة ضوئيًا ليراجعه الباحث أو أمين المتحف.',
        },
        {
          title: 'استخراج الكتابة اليدوية',
          description: 'استخدام HTR لإعداد نصوص يراجعها المختصون ويصحّحونها بالرجوع إلى الوثيقة الأصلية.',
        },
        {
          title: 'تنظيم المجموعات المراجَعة',
          description: 'جمع النصوص المتحقّق منها مع مصادرها وإتاحتها لخبراء البحث وفق ضوابط الوصول إلى المجموعة.',
        },
        {
          title: 'تعريف الزوار بالمقتنيات',
          description: 'الإجابة عن أسئلة الزوار من الأوصاف المعتمدة والمواد التي يتيحها المتحف للجمهور، مع الإحالة إلى المصدر.',
        },
      ],
      useCaseIds: ['research', 'arabic', 'visitor'],
    },
    {
      id: 'retail',
      label: 'التجزئة والتجارة الإلكترونية',
      audience: 'متاجر التجزئة · المتاجر الإلكترونية · مجموعات التجزئة',
      title: 'دعم العميل من اختيار المنتج إلى خدمة ما بعد البيع',
      description:
        'يحتاج العميل إلى إجابات عن المنتجات وطلباته دون تكرار التفاصيل لكل فريق. يربط GEEM معرفة الكتالوج وسياسات الخدمة وبيانات الطلبات المسموح بها عبر موقعك وWhatsApp وأنظمة الأعمال.',
      challenge: 'تصل معلومات المنتجات وسياسات الخدمة وتحديثات الطلبات إلى العميل من قنوات وفرق مختلفة داخل المتجر.',
      outcome: 'إجابات متسقة عن المنتجات ومتابعة أوضح للطلبات، مع مسودات محتوى تساعد الفريق على تحديث الكتالوج.',
      imageAlt: 'صاحب متجر يعمل على حاسوب محمول داخل متجر للتجزئة',
      applications: [
        {
          title: 'توضيح خيارات المنتجات',
          description: 'مساعدة العملاء على مقارنة المنتجات وفق احتياجاتهم بالاستناد إلى تفاصيل الكتالوج ومواصفاته المؤكدة.',
        },
        {
          title: 'متابعة الطلبات',
          description: 'استرجاع بيانات الطلب المسموح بها وشرح الحالة التي يعيدها نظامك.',
        },
        {
          title: 'إجراءات التوصيل والاسترجاع',
          description: 'شرح السياسة وتجهيز الطلبات المستوفية للشروط ضمن مسار الموافقات الذي أعددته.',
        },
        {
          title: 'إعداد تحديثات الكتالوج',
          description: 'صياغة أوصاف المنتجات والأسئلة الشائعة وتحديثات المحتوى من بيانات المنتجات المؤكدة، ليراجعها الفريق ويعتمدها.',
        },
      ],
      useCaseIds: ['customer', 'sales', 'arabic'],
    },
    {
      id: 'industry',
      label: 'الصناعة والخدمات اللوجستية',
      audience: 'المصانع · المستودعات · شركات الخدمات اللوجستية',
      title: 'ربط إجراءات التشغيل بالشحنات وبيانات الأجهزة',
      description:
        'قد تتوزع إجراءات التشغيل وتحديثات الشحن ومؤشرات الأجهزة بعيدًا عن الفريق الذي يتابع المشكلة. يجمع GEEM هذه المعلومات ضمن العمل، ويساعد الموظفين على إعداد المتابعة وتسليم الوردية وفق تعليمات التشغيل.',
      challenge: 'تحتاج الفرق إلى جمع الإجراءات وحالات الشحن وقراءات الأجهزة مع الحفاظ على السياق بين المواقع والورديات.',
      outcome: 'معلومات تشغيلية مترابطة تساعد على متابعة الحالات وتسليم العمل بوضوح بين الورديات والمواقع والفرق المعنية.',
      imageAlt: 'زميلان في مستودع يرتديان خوذتي سلامة وسترتين عاكستين ويراجعان جهازًا لوحيًا',
      applications: [
        {
          title: 'الوصول إلى الإجراء المناسب',
          description: 'استرجاع تعليمات التشغيل والسلامة المعتمدة من خبير مهيّأ لدور الفريق.',
        },
        {
          title: 'متابعة حالات الشحن',
          description: 'استرجاع أحدث حالة للشحنة وفق الصلاحيات وربطها بإجراء التشغيل المناسب.',
        },
        {
          title: 'ربط مؤشرات الأجهزة',
          description: 'التكامل مع أجهزة IoT والكاميرات وربط القراءات أو الملاحظات المتاحة بسياق التشغيل.',
        },
        {
          title: 'إعداد تسليم الوردية',
          description: 'تلخيص الحوادث والإجراءات المنفذة والمهام المفتوحة من السجلات المتاحة، ليراجعها الفريق قبل تسليم العمل.',
        },
      ],
      useCaseIds: ['operations', 'devices', 'employee'],
    },
    {
      id: 'facilities',
      label: 'العقارات وإدارة المرافق',
      audience: 'مشغّلو العقارات · فرق إدارة المرافق · مجمعات الأعمال',
      title: 'تحويل بلاغات المباني إلى أعمال صيانة منسّقة',
      description:
        'تسهل مراجعة بلاغ الصيانة حين تتوفر معلومات المبنى وسجل الخدمة. يساعد GEEM المستفيدين على تجهيز الطلبات، ويمد فرق المرافق بالإجراءات والأدلة وبيانات التشغيل المسموح بها لتنسيق العمل.',
      challenge: 'تتوزع بلاغات المستفيدين وأدلة المباني وتحديثات الصيانة بين فرق وأنظمة مختلفة، فيصعب جمع سياق الحالة.',
      outcome: 'طلبات أكثر اكتمالًا ومعرفة متاحة عن المبنى تساعد فرق المرافق على تنسيق المراجعة ومتابعة الصيانة.',
      imageAlt: 'مدير مرافق ومهندس صيانة يراجعان معلومات المبنى على جهاز لوحي',
      applications: [
        {
          title: 'إرشاد المستأجرين والمستفيدين',
          description: 'شرح خدمات العقار وإجراءاته من المعلومات التي يوفّرها المشغّل للسكان والمستأجرين وسائر المستفيدين.',
        },
        {
          title: 'تجهيز طلبات الصيانة',
          description: 'جمع الموقع وتفاصيل المشكلة، ثم توجيه الطلب إلى نظام الصيانة المتصل لمراجعته.',
        },
        {
          title: 'دعم متابعة المرافق',
          description: 'جمع قراءات الأجهزة وتحديثات الحالات المسموح بها لمساعدة الموظفين على تحديد الإجراء التالي.',
        },
        {
          title: 'الوصول إلى أدلة المبنى',
          description: 'مساعدة الفنيين على إيجاد دليل المعدة وإجراء الخدمة والتعليمات الخاصة بالمبنى وفق صلاحياتهم.',
        },
      ],
      useCaseIds: ['devices', 'operations', 'it'],
    },
    {
      id: 'education',
      label: 'التعليم والتدريب',
      audience: 'المدارس · الجامعات · جهات التدريب',
      title: 'مساندة التعليم والعمل الإداري',
      description:
        'يحتاج المتعلم والمعلم والموظف إلى إرشادات مختلفة من المؤسسة نفسها. يساعدهم GEEM على معرفة البرامج وإعداد المواد التعليمية وفهم إجراءات العمل، من خلال خبراء بمصادر وأدوار محددة.',
      challenge: 'يتعامل المتعلمون والموظفون مع موارد وإجراءات مختلفة، بينما يتكرر إعداد الشروح والمواد التعليمية لدى المعلمين.',
      outcome: 'إرشادات مناسبة ومسودات مراجَعة تدعم التعلم وتهيئة الموظفين الجدد واكتمال الطلبات الإدارية داخل المؤسسة التعليمية.',
      imageAlt: 'محاضر يساعد طالبًا جامعيًا على حاسوب محمول في مركز مصادر تعلم',
      applications: [
        {
          title: 'إرشاد المتعلمين',
          description: 'شرح معلومات البرامج والموارد التعليمية ومتطلبات خدمات الطلاب من مواد المؤسسة.',
        },
        {
          title: 'إعداد المواد التعليمية',
          description: 'تجهيز مسودات الشروح والملخصات والأنشطة ليراجعها المعلم أو المدرب قبل استخدامها.',
        },
        {
          title: 'دعم الطلبات الإدارية',
          description: 'مساعدة الموظفين على جمع التفاصيل المطلوبة ومتابعة الطلب ضمن مسارات الموافقات المعتمدة.',
        },
        {
          title: 'تهيئة الموظفين الجدد',
          description: 'شرح خطوات التهيئة والمسؤوليات والإجراءات الإدارية بالرجوع إلى دليل الموظف في المؤسسة.',
        },
      ],
      useCaseIds: ['arabic', 'employee', 'research'],
    },
    {
      id: 'professional',
      label: 'شركات الخدمات المهنية',
      audience: 'الشركات الاستشارية · المكاتب الهندسية · مقدّمو خدمات الأعمال',
      title: 'توظيف معرفة المشاريع في العروض وخدمة العملاء',
      description:
        'تتوزع متطلبات العملاء ومراجع المشاريع وتحديثات التنفيذ بين فرق الشركة. يساعد GEEM على إعداد العروض واسترجاع المعرفة ذات الصلة وتنسيق خدمة العميل، بالاستفادة من العمل والمراجع المتاحة.',
      challenge: 'تعيد الفرق جمع متطلبات العملاء ومراجع المشاريع وتحديثات التنفيذ من وثائق وأنظمة متعددة لكل مهمة.',
      outcome: 'معرفة قابلة لإعادة الاستخدام تساعد الفرق على إعداد المسودات وتهيئة العملاء الجدد وتنسيق طلباتهم المستمرة.',
      imageAlt: 'زملاء عمل يناقشون مشروعًا حول حاسوب محمول',
      applications: [
        {
          title: 'إعداد مسودات العروض',
          description: 'الجمع بين احتياج العميل ومعلومات خدمات الشركة لإعداد مسودة يراجعها الفريق ويرسلها.',
        },
        {
          title: 'الاستفادة من معرفة المشاريع',
          description: 'تلخيص وثائق المشاريع المسموح بها ومساعدة الفرق على الوصول إلى المراجع ذات الصلة بالمهمة.',
        },
        {
          title: 'تنسيق طلبات العملاء',
          description: 'جمع المتطلبات واسترجاع التحديثات المسموح بها من أنظمة الأعمال المتصلة.',
        },
        {
          title: 'تهيئة العملاء الجدد',
          description: 'إعداد قوائم بدء التعامل وجمع بيانات العميل المطلوبة وتلخيص الخطوات التالية المتفق عليها لتأكيدها من الفريق.',
        },
      ],
      useCaseIds: ['sales', 'developer', 'finance'],
    },
  ],
};

export function getSolutionsCopy(locale: Locale): SolutionsCopy {
  return locale === 'en' ? en : ar;
}
