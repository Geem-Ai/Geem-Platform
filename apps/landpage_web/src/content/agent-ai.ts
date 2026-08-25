import type { Locale } from '../lib/i18n';

export type AgentAiPageCopy = {
  meta: { title: string; description: string };
  hero: {
    eyebrow: string;
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
    availability: string;
  };
  toc: {
    label: string;
    items: { id: string; label: string }[];
  };
  overview: {
    eyebrow: string;
    title: string;
    description: string;
    facts: { value: string; label: string }[];
  };
  requirements: {
    eyebrow: string;
    title: string;
    description: string;
    items: string[];
    note: string;
  };
  access: {
    eyebrow: string;
    title: string;
    description: string;
    baseUrl: string;
    publicModel: string;
    requiredScope: string;
    expertHeader: string;
    modelNote: string;
    modelsTitle: string;
    modelsDescription: string;
  };
  quickstart: {
    eyebrow: string;
    title: string;
    description: string;
    requestLabel: string;
  };
  toolLoop: {
    eyebrow: string;
    title: string;
    description: string;
    steps: { title: string; description: string }[];
    replayTitle: string;
    replayDescription: string;
    billingNote: string;
  };
  sdks: {
    eyebrow: string;
    title: string;
    description: string;
    laravelTitle: string;
    laravelDescription: string;
    pythonTitle: string;
    pythonDescription: string;
  };
  streaming: {
    eyebrow: string;
    title: string;
    description: string;
    items: { title: string; description: string }[];
    metadataTitle: string;
    metadataDescription: string;
  };
  safety: {
    eyebrow: string;
    title: string;
    description: string;
    items: string[];
    warningTitle: string;
    warning: string;
  };
  controls: {
    eyebrow: string;
    title: string;
    acceptedTitle: string;
    accepted: string[];
    rejectedTitle: string;
    rejected: string[];
  };
  errors: {
    eyebrow: string;
    title: string;
    description: string;
    retry: string;
  };
  cta: {
    title: string;
    description: string;
    primary: string;
    secondary: string;
  };
  copyLabel: string;
  copiedLabel: string;
};

const en: AgentAiPageCopy = {
  meta: {
    title: 'Agents AI API documentation | Geem',
    description:
      'Integrate Geem Experts with Laravel AI or an OpenAI-compatible client while your application owns and executes every tool.',
  },
  hero: {
    eyebrow: 'Agents AI · Client Agent API',
    title: 'Build agents with your tools and Geem knowledge.',
    description:
      'Use an OpenAI Chat Completions-compatible API for client-owned tool loops. Geem grounds each model round in one Workspace Expert; your application executes every tool.',
    primaryCta: 'Open Agents AI',
    secondaryCta: 'Start integrating',
    availability: 'Paid Workspace App',
  },
  toc: {
    label: 'On this page',
    items: [
      { id: 'overview', label: 'Overview' },
      { id: 'requirements', label: 'Requirements' },
      { id: 'access', label: 'Access and models' },
      { id: 'quickstart', label: 'Quickstart' },
      { id: 'tool-loop', label: 'Tool loop and replay' },
      { id: 'sdks', label: 'SDK examples' },
      { id: 'streaming', label: 'Streaming and usage' },
      { id: 'safety', label: 'Trust and safety' },
      { id: 'controls', label: 'Supported controls' },
      { id: 'errors', label: 'Errors' },
    ],
  },
  overview: {
    eyebrow: 'Overview',
    title: 'One model round, owned by your application.',
    description:
      'Geem retrieves approved knowledge for one Expert and returns assistant text or standard tool calls. The caller owns conversation state, authorizes tools, executes them locally, and replays the resulting transcript.',
    facts: [
      { value: 'OpenAI', label: 'Chat Completions-compatible wire format' },
      { value: '1 Expert', label: 'Selected explicitly on every completion' },
      { value: '0 tools', label: 'Executed by Geem—your application stays in control' },
    ],
  },
  requirements: {
    eyebrow: 'Before the first call',
    title: 'Activate each independent access layer.',
    description:
      'A request runs only when the App, key, Expert, and Workspace allowances are all active.',
    items: [
      'Subscribe to and install the Agents AI App in the Workspace.',
      'Create or reissue an API key with the optional agent:write scope.',
      'Enable “Allow client agent API” on a Workspace-owned Expert.',
      'Keep the Workspace API RPM and AI-token allowance available.',
      'Keep the Agents AI daily request allowance available.',
    ],
    note: 'Scopes are never silently added to an existing key. Expiry or uninstall leaves the key and Expert setting stored, but makes them inert immediately.',
  },
  access: {
    eyebrow: 'Authentication',
    title: 'Use the Agent base URL and select the Expert by header.',
    description:
      'Every request uses a Workspace API key as a bearer token. Completion requests additionally require the Expert header.',
    baseUrl: 'Base URL',
    publicModel: 'Public model',
    requiredScope: 'Required key scope',
    expertHeader: 'Expert header',
    modelNote:
      'The model ID never identifies the Expert. X-Geem-Expert-Id must reference a Workspace-owned Expert available to the key’s Workspace.',
    modelsTitle: 'Discover models without consuming usage',
    modelsDescription:
      'Models list and detail require paid access and agent:write, but consume no RPM, AI-token, or daily Agents AI unit. The detail route accepts the slash inside the public model ID.',
  },
  quickstart: {
    eyebrow: 'Quickstart',
    title: 'Run one non-streaming model round.',
    description:
      'Declare the tools your application can execute. A response may contain final assistant text or choices[0].message.tool_calls.',
    requestLabel: 'cURL request',
  },
  toolLoop: {
    eyebrow: 'Caller-owned state',
    title: 'Execute tools locally, then replay the complete step.',
    description:
      'There is no hidden Geem conversation and no proprietary session header. Resend the relevant bounded history on every model step.',
    steps: [
      { title: 'Send the user turn', description: 'Include the same active tool definitions needed for this round.' },
      { title: 'Receive tool calls', description: 'Preserve every call ID, type, function name, and arguments exactly.' },
      { title: 'Authorize and execute', description: 'Validate arguments and permissions inside your application.' },
      { title: 'Replay results', description: 'Return one role: tool result for every preceding call before another user or assistant turn.' },
    ],
    replayTitle: 'Continuation transcript',
    replayDescription:
      'Parallel calls are supported. Orphaned, duplicate, incomplete, intervening, or undeclared calls are rejected before retrieval or paid admission.',
    billingNote:
      'Each HTTP completion is one billable model round and consumes one daily Agents AI unit after admission. Local tool execution is not metered by Geem.',
  },
  sdks: {
    eyebrow: 'SDKs',
    title: 'Use standard clients—no proprietary provider required.',
    description:
      'Geem continuously tests exact Laravel AI and official OpenAI SDK versions through the production Agent wire contract.',
    laravelTitle: 'Laravel AI',
    laravelDescription:
      'Use the openai-compatible driver, pin an exact package version, and provide the Expert header. v0.10.3 is the minimum supported baseline.',
    pythonTitle: 'Official OpenAI Python SDK',
    pythonDescription:
      'Set the Agent base URL and default Expert header, then use the normal Chat Completions client.',
  },
  streaming: {
    eyebrow: 'Streaming and metering',
    title: 'Standard SSE with transparent Geem metadata.',
    description:
      'Set stream: true. Tool calls arrive as indexed delta.tool_calls fragments and successful streams terminate with data: [DONE].',
    items: [
      { title: 'Usage', description: 'stream_options.include_usage adds one final usage-only chunk with raw token counts.' },
      { title: 'Geem extension', description: 'Exactly one geem object reports retrieval state, safe citations, context sufficiency, and billed tokens.' },
      { title: 'Failure after HTTP 200', description: 'The stream emits one OpenAI error frame, closes, and does not emit [DONE].' },
    ],
    metadataTitle: 'Namespaced response metadata',
    metadataDescription:
      'OpenAI-compatible clients may safely ignore geem. Never replay this extension as a conversation message.',
  },
  safety: {
    eyebrow: 'Trust boundary',
    title: 'Your application remains the tool security boundary.',
    description:
      'Client instructions and tool material are treated as untrusted input. They cannot change Workspace identity, Expert selection, access, quota, or billing.',
    items: [
      'Leading system and developer messages are demoted into one escaped, untrusted client-instruction block.',
      'Tool names, descriptions, schemas, arguments, and results must never contain credentials.',
      'Authorize every tool and validate every argument inside your own application.',
      'Enable an Expert only when the API-key holder and tool runtime may receive its knowledge.',
    ],
    warningTitle: 'Knowledge can reach tool arguments',
    warning:
      'A prompt hierarchy cannot guarantee that a model never places retrieved content in tool arguments. Treat the API key holder and its tool runtime as recipients of the selected Expert’s knowledge.',
  },
  controls: {
    eyebrow: 'Request contract',
    title: 'Unsupported behavior fails explicitly.',
    acceptedTitle: 'Accepted',
    accepted: [
      'temperature, top_p, max_tokens',
      'parallel_tool_calls',
      'stream_options.include_usage',
      'n: 1 and response_format: {"type":"text"}',
      'Function tools with object-root JSON Schema and local references',
    ],
    rejectedTitle: 'Rejected',
    rejected: [
      'Remote schema references and strict: true',
      'Structured output, vision, and audio content',
      'Legacy functions / function_call',
      'Responses API payloads',
      'Later or interleaved system/developer messages',
    ],
  },
  errors: {
    eyebrow: 'Errors',
    title: 'Every Agent route uses the OpenAI error envelope.',
    description:
      'Authentication, access, transcript, model, quota, rate, and upstream failures retain stable HTTP statuses and machine-readable codes.',
    retry:
      'Honor Retry-After on rate and quota responses. Daily quota errors also include metric, limit, used, remaining, and an RFC 3339 UTC reset_at in error.details.',
  },
  cta: {
    title: 'Ready to connect your first client-owned agent?',
    description:
      'Subscribe to Agents AI, issue a scoped key, enable one Expert, and keep tool authorization inside your application.',
    primary: 'Open Agents AI',
    secondary: 'Manage API keys',
  },
  copyLabel: 'Copy',
  copiedLabel: 'Copied',
};

const ar: AgentAiPageCopy = {
  meta: {
    title: 'توثيق واجهة Agents AI | جيم',
    description:
      'اربط خبراء جيم مع Laravel AI أو عميل متوافق مع OpenAI، مع بقاء تنفيذ الأدوات والتحكم بها داخل تطبيقك.',
  },
  hero: {
    eyebrow: 'Agents AI · واجهة وكيل العميل',
    title: 'ابنِ وكلاء بأدواتك ومعرفة جيم.',
    description:
      'استخدم واجهة متوافقة مع OpenAI Chat Completions لحلقات الأدوات التي يملكها العميل. يؤسّس جيم كل جولة نموذج على خبير واحد في مساحة العمل، بينما ينفّذ تطبيقك جميع الأدوات.',
    primaryCta: 'فتح Agents AI',
    secondaryCta: 'ابدأ التكامل',
    availability: 'تطبيق مدفوع لمساحة العمل',
  },
  toc: {
    label: 'في هذه الصفحة',
    items: [
      { id: 'overview', label: 'نظرة عامة' },
      { id: 'requirements', label: 'المتطلبات' },
      { id: 'access', label: 'الوصول والنماذج' },
      { id: 'quickstart', label: 'بدء سريع' },
      { id: 'tool-loop', label: 'حلقة الأدوات وإعادة السجل' },
      { id: 'sdks', label: 'أمثلة SDK' },
      { id: 'streaming', label: 'البث والاستخدام' },
      { id: 'safety', label: 'الثقة والأمان' },
      { id: 'controls', label: 'عناصر التحكم المدعومة' },
      { id: 'errors', label: 'الأخطاء' },
    ],
  },
  overview: {
    eyebrow: 'نظرة عامة',
    title: 'جولة نموذج واحدة يملك تطبيقك سياقها.',
    description:
      'يسترجع جيم المعرفة المعتمدة لخبير واحد، ثم يعيد نص المساعد أو استدعاءات أدوات معيارية. يملك العميل حالة المحادثة، ويصرّح الأدوات وينفّذها محلياً ثم يعيد إرسال السجل الناتج.',
    facts: [
      { value: 'OpenAI', label: 'صيغة متوافقة مع Chat Completions' },
      { value: 'خبير واحد', label: 'يُحدّد صراحة في كل طلب إكمال' },
      { value: '0 أدوات', label: 'ينفّذها جيم—يبقى التحكم داخل تطبيقك' },
    ],
  },
  requirements: {
    eyebrow: 'قبل أول طلب',
    title: 'فعّل كل طبقة وصول مستقلة.',
    description:
      'لا يعمل الطلب إلا عندما يكون التطبيق والمفتاح والخبير وحصص مساحة العمل جميعها فعّالة.',
    items: [
      'اشترك في تطبيق Agents AI وثبّته في مساحة العمل.',
      'أنشئ مفتاح API أو أعد إصداره مع نطاق agent:write الاختياري.',
      'فعّل «السماح لواجهة وكيل العميل» في خبير مملوك لمساحة العمل.',
      'تأكد من توفر حد طلبات API بالدقيقة وحصة رموز الذكاء الاصطناعي.',
      'تأكد من توفر الحصة اليومية لطلبات Agents AI.',
    ],
    note: 'لا تُضاف النطاقات تلقائياً إلى مفتاح قائم. انتهاء الاشتراك أو إلغاء التثبيت يُبقي المفتاح وإعداد الخبير محفوظين، لكنهما يصبحان غير فعّالين فوراً.',
  },
  access: {
    eyebrow: 'المصادقة',
    title: 'استخدم عنوان Agent وحدّد الخبير عبر الترويسة.',
    description:
      'يستخدم كل طلب مفتاح مساحة العمل كترويسة Bearer. وتتطلب طلبات الإكمال أيضاً ترويسة الخبير.',
    baseUrl: 'العنوان الأساسي',
    publicModel: 'النموذج العام',
    requiredScope: 'نطاق المفتاح المطلوب',
    expertHeader: 'ترويسة الخبير',
    modelNote:
      'معرّف النموذج لا يحدّد الخبير. يجب أن يشير X-Geem-Expert-Id إلى خبير مملوك لمساحة العمل المرتبطة بالمفتاح.',
    modelsTitle: 'اكتشف النماذج دون استهلاك الحصة',
    modelsDescription:
      'تتطلب مسارات قائمة النماذج وتفاصيلها وصولاً مدفوعاً ونطاق agent:write، لكنها لا تستهلك حد الدقيقة أو الرموز أو الحصة اليومية. يقبل مسار التفاصيل الشرطة المائلة داخل معرّف النموذج.',
  },
  quickstart: {
    eyebrow: 'بدء سريع',
    title: 'نفّذ جولة نموذج واحدة دون بث.',
    description:
      'عرّف الأدوات التي يستطيع تطبيقك تنفيذها. قد تحتوي الاستجابة على نص نهائي أو choices[0].message.tool_calls.',
    requestLabel: 'طلب cURL',
  },
  toolLoop: {
    eyebrow: 'حالة يملكها العميل',
    title: 'نفّذ الأدوات محلياً، ثم أعد إرسال الخطوة كاملة.',
    description:
      'لا توجد محادثة مخفية في جيم ولا ترويسة جلسة خاصة. أعد إرسال السجل المحدود ذي الصلة في كل خطوة نموذج.',
    steps: [
      { title: 'أرسل رسالة المستخدم', description: 'ضمّن تعريفات الأدوات الفعّالة نفسها اللازمة لهذه الجولة.' },
      { title: 'استقبل استدعاءات الأدوات', description: 'احتفظ بمعرّف كل استدعاء ونوعه واسم الدالة ووسائطها كما هي.' },
      { title: 'صرّح ونفّذ', description: 'تحقق من الوسائط والصلاحيات داخل تطبيقك.' },
      { title: 'أعد نتائج الأدوات', description: 'أرسل نتيجة role: tool واحدة لكل استدعاء سابق قبل أي رسالة مستخدم أو مساعد جديدة.' },
    ],
    replayTitle: 'سجل الاستكمال',
    replayDescription:
      'الاستدعاءات المتوازية مدعومة. تُرفض الاستدعاءات اليتيمة أو المكررة أو الناقصة أو غير المعلنة قبل الاسترجاع أو قبول الفوترة.',
    billingNote:
      'كل طلب إكمال عبر HTTP هو جولة نموذج قابلة للفوترة ويستهلك وحدة يومية واحدة بعد القبول. تنفيذ الأدوات محلياً لا يقيسه جيم.',
  },
  sdks: {
    eyebrow: 'حزم التطوير',
    title: 'استخدم العملاء المعياريين دون مزود خاص.',
    description:
      'يختبر جيم باستمرار إصدارات محددة من Laravel AI وحزمة OpenAI الرسمية عبر عقد Agent الفعلي.',
    laravelTitle: 'Laravel AI',
    laravelDescription:
      'استخدم مزود openai-compatible وثبّت إصداراً محدداً وأرسل ترويسة الخبير. الإصدار v0.10.3 هو الحد الأدنى المدعوم.',
    pythonTitle: 'حزمة OpenAI الرسمية لـ Python',
    pythonDescription:
      'اضبط عنوان Agent وترويسة الخبير الافتراضية، ثم استخدم عميل Chat Completions المعتاد.',
  },
  streaming: {
    eyebrow: 'البث والقياس',
    title: 'بث SSE معياري مع بيانات جيم واضحة.',
    description:
      'اضبط stream: true. تصل استدعاءات الأدوات كأجزاء delta.tool_calls مفهرسة، وتنتهي الاستجابة الناجحة بـ data: [DONE].',
    items: [
      { title: 'الاستخدام', description: 'يضيف stream_options.include_usage جزءاً نهائياً واحداً يحوي أعداد الرموز الخام.' },
      { title: 'امتداد جيم', description: 'يظهر كائن geem مرة واحدة ويعرض حالة الاسترجاع والمصادر الآمنة وكفاية السياق والرموز المفوترة.' },
      { title: 'فشل بعد HTTP 200', description: 'يبث الخادم إطار خطأ OpenAI واحداً ثم يغلق دون إرسال [DONE].' },
    ],
    metadataTitle: 'بيانات استجابة ضمن نطاق geem',
    metadataDescription:
      'يمكن لعملاء OpenAI تجاهل geem بأمان. لا تُعد هذا الامتداد كرسالة في المحادثة.',
  },
  safety: {
    eyebrow: 'حدود الثقة',
    title: 'يبقى تطبيقك هو حد أمان الأدوات.',
    description:
      'تعامل جيم تعليمات العميل ومواد الأدوات كمدخلات غير موثوقة. ولا يمكنها تغيير هوية مساحة العمل أو الخبير أو الوصول أو الحصص أو الفوترة.',
    items: [
      'تُخفّض رسائل system وdeveloper الأولية إلى كتلة تعليمات عميل واحدة مهروبة وغير موثوقة.',
      'يجب ألا تحتوي أسماء الأدوات أو أوصافها أو مخططاتها أو وسائطها أو نتائجها على بيانات اعتماد.',
      'صرّح كل أداة وتحقق من كل وسيط داخل تطبيقك.',
      'فعّل الخبير فقط عندما يُسمح لحامل المفتاح وبيئة الأدوات باستلام معرفته.',
    ],
    warningTitle: 'قد تصل المعرفة إلى وسائط الأدوات',
    warning:
      'لا يضمن تسلسل التعليمات ألا يضع النموذج محتوى مسترجعاً داخل وسائط الأداة. اعتبر حامل المفتاح وبيئة أدواته مستلمين لمعرفة الخبير المحدد.',
  },
  controls: {
    eyebrow: 'عقد الطلب',
    title: 'السلوك غير المدعوم يفشل بوضوح.',
    acceptedTitle: 'مدعوم',
    accepted: [
      'temperature وtop_p وmax_tokens',
      'parallel_tool_calls',
      'stream_options.include_usage',
      'n: 1 وresponse_format: {"type":"text"}',
      'أدوات الدوال بمخطط JSON ذي جذر object ومراجع محلية',
    ],
    rejectedTitle: 'مرفوض',
    rejected: [
      'مراجع المخطط البعيدة وstrict: true',
      'المخرجات المنظمة ومحتوى الصور والصوت',
      'functions / function_call القديمة',
      'طلبات Responses API',
      'رسائل system/developer المتأخرة أو المتداخلة',
    ],
  },
  errors: {
    eyebrow: 'الأخطاء',
    title: 'تستخدم جميع مسارات Agent غلاف أخطاء OpenAI.',
    description:
      'تحافظ أخطاء المصادقة والوصول والسجل والنموذج والحصص والمعدل والمزود على حالات HTTP ورموز قابلة للمعالجة آلياً.',
    retry:
      'احترم Retry-After في استجابات المعدل والحصة. تتضمن أخطاء الحصة اليومية أيضاً metric وlimit وused وremaining ووقت reset_at بصيغة RFC 3339 UTC داخل error.details.',
  },
  cta: {
    title: 'جاهز لربط أول وكيل يملكه تطبيقك؟',
    description:
      'اشترك في Agents AI، وأصدر مفتاحاً بالنطاق المطلوب، وفعّل خبيراً واحداً، وأبقِ تصريح الأدوات داخل تطبيقك.',
    primary: 'فتح Agents AI',
    secondary: 'إدارة مفاتيح API',
  },
  copyLabel: 'نسخ',
  copiedLabel: 'تم النسخ',
};

export function getAgentAiCopy(locale: Locale): AgentAiPageCopy {
  return locale === 'en' ? en : ar;
}
