import type { Locale } from '../lib/i18n';

export type UseCaseId = 'customer' | 'employee' | 'operations' | 'sales' | 'finance' | 'it' | 'research';

type UseCase = {
  id: UseCaseId;
  label: string;
  channel: string;
  title: string;
  description: string;
  question: string;
  imageAlt: string;
  steps: { label: string; description: string }[];
};

export type UseCasesCopy = {
  eyebrow: string;
  title: string;
  description: string;
  tabsLabel: string;
  exampleLabel: string;
  requestLabel: string;
  flowLabel: string;
  note: string;
  cases: UseCase[];
};

const en: UseCasesCopy = {
  eyebrow: 'Geem at work',
  title: 'Explore Geem across your business',
  description:
    'From serving customers and supporting teams to digitizing research collections, explore how Geem connects knowledge with practical work.',
  tabsLabel: 'Explore a business use case',
  exampleLabel: 'Illustrative workflow',
  requestLabel: 'A conversation starts here',
  flowLabel: 'How the workflow can work',
  note:
    'These workflows are illustrative. Connected actions require configured integrations, access checks and approvals, and are executed by your application or a connected service. The Expert reports the returned result or what needs attention. Researchers or curators review recognized text before adding it to a knowledge collection.',
  cases: [
    {
      id: 'customer',
      label: 'Customer service',
      channel: 'Website · WhatsApp',
      title: 'Keep your customer’s request moving',
      description:
        'Combine service policies with current order information to guide a customer through a delivery request.',
      question: 'Can I change the delivery date for my order?',
      imageAlt: 'A male shop owner using a phone and laptop in his store.',
      steps: [
        { label: 'Context', description: 'Delivery policy and the customer’s request.' },
        { label: 'Expert', description: 'Explains the options and gathers the details.' },
        { label: 'System', description: 'Checks access and eligibility before submitting a change.' },
        { label: 'Result', description: 'Shares the confirmed update or the next available step.' },
      ],
    },
    {
      id: 'employee',
      label: 'Employee support',
      channel: 'Workspace chat · Internal apps',
      title: 'Make leave requests easier to navigate',
      description:
        'Help employees understand the leave policy, prepare a request and follow its progress through your approval process.',
      question: 'How can I request annual leave for next month?',
      imageAlt: 'Three male colleagues reviewing information together in an office.',
      steps: [
        { label: 'Context', description: 'Leave policy and the employee’s preferred dates.' },
        { label: 'Expert', description: 'Explains the requirements and gathers the request details.' },
        { label: 'System', description: 'Checks permissions and submits the leave request for approval.' },
        { label: 'Result', description: 'Returns the request reference and its approval status.' },
      ],
    },
    {
      id: 'operations',
      label: 'Operations',
      channel: 'Business apps · Workspace chat',
      title: 'Put working knowledge close to the work',
      description:
        'Connect operating procedures with an authorized system lookup to help a team investigate a shipment exception.',
      question: 'This shipment is delayed. What should I do next?',
      imageAlt: 'Two male warehouse workers wearing hard hats and safety vests.',
      steps: [
        { label: 'Context', description: 'Shipping procedures and the reported exception.' },
        { label: 'Expert', description: 'Identifies the shipment and the information needed.' },
        { label: 'System', description: 'Checks access and retrieves the latest shipment status.' },
        { label: 'Result', description: 'Explains the returned status and the relevant procedure.' },
      ],
    },
    {
      id: 'sales',
      label: 'Sales',
      channel: 'Workspace chat · Sales apps',
      title: 'Turn a customer brief into a proposal draft',
      description:
        'Use your approved catalogue and authorized CRM information to prepare a proposal that your sales team reviews and sends.',
      question: 'Prepare a proposal draft for this customer.',
      imageAlt: 'Two male business colleagues working together on a sales proposal.',
      steps: [
        { label: 'Context', description: 'Approved catalogue and the customer’s requirements.' },
        { label: 'Expert', description: 'Identifies the scope and customer information needed.' },
        { label: 'System', description: 'Checks access and retrieves the permitted CRM details.' },
        { label: 'Result', description: 'Prepares a draft for a salesperson to review and send.' },
      ],
    },
    {
      id: 'finance',
      label: 'Finance',
      channel: 'Workspace chat · Finance apps',
      title: 'Guide an expense claim from policy to review',
      description:
        'Help employees understand expense rules and prepare a claim for your finance team to review.',
      question: 'How do I claim this business travel expense?',
      imageAlt: 'A male accountant reviewing financial documents at his desk.',
      steps: [
        { label: 'Context', description: 'Expense policy, claim details and supporting documents.' },
        { label: 'Expert', description: 'Explains the requirements and gathers the claim information.' },
        { label: 'System', description: 'Checks permissions and submits the claim for review.' },
        { label: 'Result', description: 'Returns the claim reference and review status. No payment is initiated.' },
      ],
    },
    {
      id: 'it',
      label: 'IT support',
      channel: 'Workspace chat · Internal apps',
      title: 'Give application access requests a clear path',
      description:
        'Guide employees through your application access process while keeping access decisions within your existing approval workflow.',
      question: 'How do I request access to a work application?',
      imageAlt: 'A male IT technician working beside server racks.',
      steps: [
        { label: 'Context', description: 'IT guidance and application access policies.' },
        { label: 'Expert', description: 'Identifies the application and gathers the required details.' },
        { label: 'System', description: 'Creates a permitted request through your approval process.' },
        { label: 'Result', description: 'Returns the request status; access requires the configured approval.' },
      ],
    },
    {
      id: 'research',
      label: 'Research & museums',
      channel: 'Documents · Knowledge collections',
      title: 'Turn printed and handwritten records into usable knowledge',
      description:
        'Geem uses OCR for printed text and HTR for handwriting to help research centres and museums digitize documents, review transcriptions and organize their collections.',
      question: 'Transcribe these documents so our team can review and organize them.',
      imageAlt: 'A male researcher working with a document scanner in a museum archive.',
      steps: [
        { label: 'Source', description: 'Scanned printed documents and handwritten records.' },
        { label: 'Recognition', description: 'Geem extracts printed text with OCR and handwriting with HTR.' },
        { label: 'Review', description: 'A researcher or curator checks and corrects the transcription.' },
        { label: 'Use', description: 'Organize reviewed text in a knowledge collection for research and reference.' },
      ],
    },
  ],
};

const ar: UseCasesCopy = {
  eyebrow: 'جيم في أعمالك',
  title: 'اكتشف استخدامات جيم في أعمالك',
  description:
    'من خدمة العملاء ودعم الفرق إلى رقمنة الوثائق والمجموعات البحثية، اكتشف كيف يحوّل جيم المعرفة إلى مساعدة عملية.',
  tabsLabel: 'اختر استخدامًا لجيم',
  exampleLabel: 'مثال توضيحي',
  requestLabel: 'طلب المستخدم',
  flowLabel: 'خطوات العمل',
  note:
    'هذه المسارات أمثلة توضيحية. تتطلب الإجراءات المرتبطة بالأنظمة إعداد التكاملات والصلاحيات والموافقات المناسبة، وينفّذها تطبيقك أو الخدمة المتصلة. يعرض الخبير النتيجة الواردة أو ما يحتاج إلى متابعة. ويراجع الباحث أو أمين المتحف النصوص المستخرجة قبل إضافتها إلى مجموعة معرفية.',
  cases: [
    {
      id: 'customer',
      label: 'خدمة العملاء',
      channel: 'الموقع الإلكتروني · واتساب',
      title: 'ساعد عميلك على متابعة طلبه',
      description:
        'استعن بسياسات الخدمة وبيانات الطلب الحالية لمساعدة العميل على طلب تغيير موعد التوصيل.',
      question: 'هل يمكنني تغيير موعد توصيل طلبي؟',
      imageAlt: 'صاحب متجر يستخدم هاتفًا وحاسوبًا محمولًا داخل متجره.',
      steps: [
        { label: 'المعرفة', description: 'سياسة التوصيل وتفاصيل طلب العميل.' },
        { label: 'الخبير', description: 'يشرح الخيارات ويجمع المعلومات اللازمة.' },
        { label: 'النظام', description: 'يتحقق من الصلاحيات واستيفاء الشروط قبل إرسال طلب التعديل.' },
        { label: 'النتيجة', description: 'يعرض التحديث الذي أكّده النظام أو الخطوة التالية المتاحة.' },
      ],
    },
    {
      id: 'employee',
      label: 'دعم الموظفين',
      channel: 'محادثة جيم · التطبيقات الداخلية',
      title: 'وضّح لموظفيك خطوات طلب الإجازة',
      description:
        'ساعد الموظفين على فهم سياسة الإجازات وتجهيز طلباتهم ومتابعتها ضمن مسار الموافقات المعتمد.',
      question: 'كيف أقدّم طلب إجازة سنوية للشهر القادم؟',
      imageAlt: 'ثلاثة زملاء رجال يراجعون المعلومات معًا في مكتب.',
      steps: [
        { label: 'المعرفة', description: 'سياسة الإجازات والتواريخ التي يطلبها الموظف.' },
        { label: 'الخبير', description: 'يشرح المتطلبات ويجمع تفاصيل طلب الإجازة.' },
        { label: 'النظام', description: 'يتحقق من الصلاحيات ويرسل طلب الإجازة للموافقة.' },
        { label: 'النتيجة', description: 'يعرض رقم الطلب وحالة الموافقة عليه.' },
      ],
    },
    {
      id: 'operations',
      label: 'العمليات',
      channel: 'تطبيقات الأعمال · محادثة جيم',
      title: 'ساعد فريقك على متابعة الشحنات',
      description:
        'اربط إجراءات التشغيل ببيانات الشحن المتاحة وفق صلاحيات فريقك، لمساعدته على متابعة شحنة متأخرة.',
      question: 'تأخرت هذه الشحنة، ما الخطوة التالية؟',
      imageAlt: 'عاملان في مستودع يرتديان خوذات وسترات سلامة.',
      steps: [
        { label: 'المعرفة', description: 'إجراءات الشحن وتفاصيل الحالة المبلّغ عنها.' },
        { label: 'الخبير', description: 'يحدّد الشحنة والمعلومات اللازمة للمتابعة.' },
        { label: 'النظام', description: 'يتحقق من الصلاحيات ويسترجع أحدث حالة للشحنة.' },
        { label: 'النتيجة', description: 'يوضّح الحالة الواردة من النظام والإجراء المناسب.' },
      ],
    },
    {
      id: 'sales',
      label: 'المبيعات',
      channel: 'محادثة جيم · تطبيقات المبيعات',
      title: 'من احتياج العميل إلى مسودة عرض',
      description:
        'استعن بدليل المنتجات والخدمات المعتمد وبيانات إدارة العملاء المصرّح بها لتجهيز عرض يراجعه فريق المبيعات ويرسله.',
      question: 'جهّز مسودة عرض لهذا العميل.',
      imageAlt: 'زميلان في العمل يجهّزان عرضًا لعميل.',
      steps: [
        { label: 'المعرفة', description: 'دليل المنتجات والخدمات المعتمد واحتياجات العميل.' },
        { label: 'الخبير', description: 'يحدّد نطاق العرض وبيانات العميل المطلوبة.' },
        { label: 'النظام', description: 'يتحقق من الصلاحيات ويسترجع البيانات المسموح بها من نظام إدارة العملاء.' },
        { label: 'النتيجة', description: 'يجهّز مسودة يراجعها مسؤول المبيعات ويرسلها.' },
      ],
    },
    {
      id: 'finance',
      label: 'المالية',
      channel: 'محادثة جيم · التطبيقات المالية',
      title: 'من سياسة المصروفات إلى مطالبة جاهزة للمراجعة',
      description:
        'ساعد الموظفين على فهم ضوابط المصروفات وتجهيز مطالباتهم لمراجعتها من الفريق المالي.',
      question: 'كيف أقدّم مطالبة بمصروفات رحلة العمل؟',
      imageAlt: 'محاسب يراجع مستندات مالية على مكتبه.',
      steps: [
        { label: 'المعرفة', description: 'سياسة المصروفات وتفاصيل المطالبة والمستندات المؤيدة.' },
        { label: 'الخبير', description: 'يشرح المتطلبات ويجمع بيانات المطالبة.' },
        { label: 'النظام', description: 'يتحقق من الصلاحيات ويرسل المطالبة للمراجعة.' },
        { label: 'النتيجة', description: 'يعرض رقم المطالبة وحالة مراجعتها، دون بدء أي عملية دفع.' },
      ],
    },
    {
      id: 'it',
      label: 'الدعم التقني',
      channel: 'محادثة جيم · التطبيقات الداخلية',
      title: 'مسار واضح لطلب صلاحيات التطبيقات',
      description:
        'أرشد الموظفين إلى طريقة طلب صلاحية استخدام التطبيقات، مع إبقاء قرار منحها ضمن مسار الموافقات المعتمد.',
      question: 'كيف أطلب صلاحية استخدام أحد تطبيقات العمل؟',
      imageAlt: 'فني تقنية معلومات يعمل بجانب رفوف الخوادم.',
      steps: [
        { label: 'المعرفة', description: 'إرشادات تقنية المعلومات وسياسات استخدام التطبيقات.' },
        { label: 'الخبير', description: 'يحدّد التطبيق ويجمع المعلومات المطلوبة.' },
        { label: 'النظام', description: 'ينشئ طلبًا وفق الصلاحيات ومسار الموافقات المحدد.' },
        { label: 'النتيجة', description: 'يعرض حالة الطلب، ويتطلب منح الصلاحية الموافقة المحددة.' },
      ],
    },
    {
      id: 'research',
      label: 'الأبحاث والمتاحف',
      channel: 'الوثائق · المجموعات المعرفية',
      title: 'من الوثائق والمخطوطات إلى معرفة رقمية',
      description:
        'يستخرج جيم النصوص المطبوعة باستخدام OCR، والنصوص المكتوبة بخط اليد باستخدام HTR، لمساعدة مراكز الأبحاث والمتاحف على رقمنة وثائقها ومراجعتها وتنظيمها.',
      question: 'استخرج نصوص هذه الوثائق ليتمكن فريقنا من مراجعتها وتنظيمها.',
      imageAlt: 'باحث يعمل على ماسح ضوئي للوثائق في أرشيف متحف.',
      steps: [
        { label: 'المصدر', description: 'صور ممسوحة ضوئيًا لوثائق مطبوعة وأخرى مكتوبة بخط اليد.' },
        { label: 'التعرّف', description: 'يستخرج جيم النص المطبوع باستخدام OCR والمكتوب بخط اليد باستخدام HTR.' },
        { label: 'المراجعة', description: 'يراجع الباحث أو أمين المتحف النص المستخرج ويصحّحه.' },
        { label: 'الاستخدام', description: 'نظّم النصوص بعد مراجعتها ضمن مجموعة معرفية للبحث والرجوع إليها.' },
      ],
    },
  ],
};

export function getUseCasesCopy(locale: Locale): UseCasesCopy {
  return locale === 'en' ? en : ar;
}
