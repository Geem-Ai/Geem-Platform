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
    title: 'دليل التكامل مع Agents AI | جيم',
    description:
      'اربط تطبيقك بخبراء جيم عبر Laravel AI أو أي عميل متوافق مع OpenAI، مع بقاء تنفيذ الأدوات وصلاحياتها تحت تحكمك.',
  },
  hero: {
    eyebrow: 'Agents AI · واجهة الوكلاء للتطبيقات',
    title: 'ابنِ وكلاء ذكاء اصطناعي تستفيد من أدوات تطبيقك ومعرفة جيم.',
    description:
      'استخدم واجهة متوافقة مع OpenAI Chat Completions لبناء وكيل يستفيد من أدوات تطبيقك. يزوّد جيم كل طلب بمعرفة خبير واحد من مساحة العمل، ويبقى القرار بشأن وقت تنفيذ الأدوات وطريقة تنفيذها بيد تطبيقك.',
    primaryCta: 'افتح Agents AI',
    secondaryCta: 'ابدأ التكامل',
    availability: 'متاح باشتراك مدفوع في متجر جيم',
  },
  toc: {
    label: 'في هذه الصفحة',
    items: [
      { id: 'overview', label: 'نظرة عامة' },
      { id: 'requirements', label: 'المتطلبات' },
      { id: 'access', label: 'الوصول والنماذج' },
      { id: 'quickstart', label: 'بدء سريع' },
      { id: 'tool-loop', label: 'آلية عمل الأدوات' },
      { id: 'sdks', label: 'أمثلة حزم التطوير' },
      { id: 'streaming', label: 'البث واحتساب الاستخدام' },
      { id: 'safety', label: 'الأمان وحدود الثقة' },
      { id: 'controls', label: 'الخيارات المدعومة' },
      { id: 'errors', label: 'الأخطاء' },
    ],
  },
  overview: {
    eyebrow: 'نظرة عامة',
    title: 'جيم يدير جولة النموذج، وتطبيقك يتولى تنفيذ الأدوات.',
    description:
      'يبحث جيم في المصادر المعتمدة لدى الخبير، ثم يعيد إجابة نصية أو طلبات لاستدعاء أدواتك. يحتفظ تطبيقك بسجل المحادثة، ويتحقق من صلاحية كل أداة، وينفّذها محليًا، ثم يرسل النتيجة في الطلب التالي.',
    facts: [
      { value: 'OpenAI', label: 'طلبات واستجابات متوافقة مع Chat Completions' },
      { value: 'خبير واحد', label: 'تحدّده بوضوح في كل طلب إكمال' },
      { value: 'صفر', label: 'أداة ينفّذها جيم؛ التنفيذ داخل تطبيقك فقط' },
    ],
  },
  requirements: {
    eyebrow: 'قبل أول طلب',
    title: 'جهّز الوصول قبل إرسال أول طلب.',
    description:
      'لا يُنفّذ الطلب إلا إذا كان الاشتراك والمفتاح والخبير وحصص الاستخدام كلها جاهزة.',
    items: [
      'اشترك في تطبيق Agents AI وثبّته في مساحة العمل.',
      'أنشئ مفتاح API جديدًا، أو أعد إصدار مفتاح قائم، مع تفعيل نطاق agent:write.',
      'فعّل خيار «السماح بواجهة وكيل العميل» في خبير تملكه مساحة العمل.',
      'تأكد من وجود سعة متاحة ضمن حد طلبات API في الدقيقة وحصة رموز الذكاء الاصطناعي.',
      'تأكد من وجود سعة متاحة ضمن الحصة اليومية لطلبات Agents AI.',
    ],
    note: 'لا يضيف جيم نطاقًا جديدًا إلى مفتاح قائم تلقائيًا. إذا انتهى الاشتراك أو ألغيت تثبيت التطبيق، فيبقى المفتاح وإعداد الخبير محفوظين، لكن الوصول يتوقف فورًا.',
  },
  access: {
    eyebrow: 'المصادقة',
    title: 'استخدم عنوان واجهة Agent، وحدّد الخبير في ترويسة الطلب.',
    description:
      'أرسل مفتاح API الخاص بمساحة العمل في ترويسة Authorization بصيغة Bearer. وفي طلبات الإكمال، أضف أيضًا ترويسة الخبير.',
    baseUrl: 'عنوان الواجهة',
    publicModel: 'معرّف النموذج',
    requiredScope: 'النطاق المطلوب للمفتاح',
    expertHeader: 'ترويسة الخبير',
    modelNote:
      'معرّف النموذج ليس معرّف الخبير. استخدم X-Geem-Expert-Id للإشارة إلى خبير تملكه مساحة العمل المرتبطة بالمفتاح.',
    modelsTitle: 'استعرض النماذج من دون استهلاك الحصص',
    modelsDescription:
      'تتطلب قائمة النماذج وصفحة تفاصيل النموذج اشتراكًا فعالًا ونطاق agent:write، لكنها لا تخصم من حد الطلبات في الدقيقة أو حصة الرموز أو الحصة اليومية. ويمكن أن يحتوي معرّف النموذج في مسار التفاصيل على شرطة مائلة.',
  },
  quickstart: {
    eyebrow: 'ابدأ الآن',
    title: 'أرسل أول طلب إكمال من دون بث.',
    description:
      'أرسل إلى النموذج تعريف الأدوات التي يستطيع تطبيقك تنفيذها. وستحصل في الاستجابة على نص نهائي من المساعد، أو على طلبات أدوات داخل choices[0].message.tool_calls.',
    requestLabel: 'طلب cURL',
  },
  toolLoop: {
    eyebrow: 'تطبيقك يدير المحادثة',
    title: 'نفّذ الأداة في تطبيقك، ثم أرسل النتيجة إلى جيم.',
    description:
      'لا يحتفظ جيم بمحادثة مخفية، ولا تحتاج إلى ترويسة جلسة خاصة. في كل جولة، أرسل الجزء المطلوب من سجل المحادثة من جديد.',
    steps: [
      { title: 'أرسل سؤال المستخدم', description: 'أرفق تعريفات الأدوات المتاحة لهذه الجولة.' },
      { title: 'استقبل طلبات الأدوات', description: 'احتفظ بمعرّف كل طلب ونوعه واسم الدالة ووسائطها من دون تعديل.' },
      { title: 'تحقق ثم نفّذ', description: 'تحقق من الوسائط ومن صلاحية المستخدم قبل تنفيذ الأداة داخل تطبيقك.' },
      { title: 'أعد إرسال النتائج', description: 'أرسل رسالة واحدة بدور role: tool لكل طلب أداة، ثم تابع المحادثة.' },
    ],
    replayTitle: 'سجل الطلب التالي',
    replayDescription:
      'يمكن للنموذج طلب عدة أدوات بالتوازي. يجب أن تعيد نتيجة واحدة لكل طلب قبل إضافة رسالة مستخدم أو مساعد جديدة. يرفض جيم الطلبات الناقصة أو المكررة أو غير المعلنة قبل استرجاع المعرفة أو احتساب الاستخدام.',
    billingNote:
      'يُحتسب كل طلب إكمال عبر HTTP كجولة نموذج واحدة، ويخصم وحدة واحدة من الحصة اليومية بعد قبوله. أما تنفيذ الأداة داخل تطبيقك فلا يحتسبه جيم.',
  },
  sdks: {
    eyebrow: 'حزم التطوير',
    title: 'استخدم الحزم المعتادة؛ لا تحتاج إلى مزود مخصص.',
    description:
      'يختبر جيم إصدارات محددة من Laravel AI وحزمة OpenAI الرسمية مباشرةً مع واجهة Agent، لضمان توافق التكامل مع السلوك الفعلي.',
    laravelTitle: 'Laravel AI',
    laravelDescription:
      'استخدم المشغّل openai-compatible، وثبّت إصدار الحزمة بدقة، وأرسل ترويسة الخبير. الإصدار v0.10.3 هو أقدم إصدار مدعوم.',
    pythonTitle: 'حزمة OpenAI الرسمية لـ Python',
    pythonDescription:
      'اضبط عنوان Agent وترويسة الخبير الافتراضية، ثم استخدم Chat Completions بالطريقة المعتادة.',
  },
  streaming: {
    eyebrow: 'البث واحتساب الاستخدام',
    title: 'بث SSE قياسي مع بيانات استخدام واضحة.',
    description:
      'عند ضبط stream: true، تصل طلبات الأدوات على أجزاء مفهرسة داخل delta.tool_calls، وتنتهي الاستجابة الناجحة بالرسالة data: [DONE].',
    items: [
      { title: 'بيانات الاستخدام', description: 'يرسل stream_options.include_usage جزءًا واحدًا في نهاية البث، ويتضمن عدد رموز النموذج الفعلي.' },
      { title: 'بيانات جيم الإضافية', description: 'يظهر كائن geem مرة واحدة، ويعرض حالة الاسترجاع والمصادر الآمنة وكفاية السياق والرموز المحتسبة.' },
      { title: 'خطأ بعد بدء البث', description: 'إذا حدث خطأ بعد HTTP 200، يرسل الخادم إطار خطأ واحدًا بصيغة OpenAI، ثم يغلق البث من دون [DONE].' },
    ],
    metadataTitle: 'بيانات جيم المصاحبة للاستجابة',
    metadataDescription:
      'يمكن لأي عميل متوافق مع OpenAI تجاهل كائن geem بأمان. لا ترسل هذا الكائن مرة أخرى ضمن رسائل المحادثة.',
  },
  safety: {
    eyebrow: 'الأمان وحدود الثقة',
    title: 'تطبيقك هو المسؤول عن أمان الأدوات.',
    description:
      'يتعامل جيم مع تعليمات العميل وتعريفات الأدوات ونتائجها كمدخلات غير موثوقة. ولا تستطيع هذه المدخلات تغيير مساحة العمل أو الخبير أو صلاحيات الوصول أو الحصص أو الفوترة.',
    items: [
      'يخفّض جيم أولوية رسائل system وdeveloper الموجودة في بداية المحادثة، ويجمعها بعد معالجتها بأمان في كتلة واحدة موسومة بوضوح بأنها تعليمات عميل غير موثوقة.',
      'لا تضع بيانات اعتماد أو أسرارًا في اسم الأداة أو وصفها أو مخططها أو وسائطها أو نتائجها.',
      'تحقق من صلاحية كل أداة ومن صحة كل وسيط قبل التنفيذ داخل تطبيقك.',
      'لا تفعّل الخبير إلا إذا كان مسموحًا لحامل المفتاح وبيئة تشغيل الأدوات بالاطلاع على معرفته.',
    ],
    warningTitle: 'قد يضمّن النموذج جزءًا من المعرفة في وسائط الأداة',
    warning:
      'لا يمكن لمنظومة التعليمات أن تمنع ذلك دائمًا. لذلك اعتبر حامل المفتاح وبيئة تشغيل أدواته جهتين مخوّلتين بالاطلاع على معرفة الخبير المحدد.',
  },
  controls: {
    eyebrow: 'ما الذي تقبله الواجهة؟',
    title: 'تقبل الواجهة الخيارات التالية، وتعيد خطأً واضحًا لأي خيار آخر.',
    acceptedTitle: 'خيارات مدعومة',
    accepted: [
      'temperature وtop_p وmax_tokens',
      'parallel_tool_calls',
      'stream_options.include_usage',
      'n: 1 وresponse_format: {"type":"text"}',
      'أدوات الدوال بمخطط JSON يبدأ بكائن object ويستخدم مراجع محلية',
    ],
    rejectedTitle: 'خيارات غير مدعومة',
    rejected: [
      'مراجع المخطط الخارجية وخيار strict: true',
      'المخرجات المنظمة أو محتوى الصور والصوت',
      'واجهتا functions وfunction_call القديمتان',
      'طلبات واجهة Responses API',
      'رسائل system أو developer التي تظهر بعد بدء المحادثة',
    ],
  },
  errors: {
    eyebrow: 'الأخطاء',
    title: 'تعيد جميع مسارات Agent الأخطاء بصيغة OpenAI.',
    description:
      'يعيد كل خطأ حالة HTTP ورمزًا ثابتًا يمكن لتطبيقك التعامل معهما، سواء كان الخطأ مرتبطًا بالمصادقة أو الوصول أو سجل المحادثة أو النموذج أو الحصة أو مزود الخدمة.',
    retry:
      'التزم بقيمة Retry-After عند تجاوز معدل الطلبات أو الحصة. ويتضمن خطأ الحصة اليومية داخل error.details الحقول metric وlimit وused وremaining، إضافةً إلى reset_at بتوقيت UTC وبتنسيق RFC 3339.',
  },
  cta: {
    title: 'جاهز لربط أول وكيل بتطبيقك؟',
    description:
      'اشترك في Agents AI، وأنشئ مفتاحًا بالنطاق المطلوب، وفعّل خبيرًا، ثم دع تطبيقك يقرر متى تُنفّذ الأدوات وكيف.',
    primary: 'افتح Agents AI',
    secondary: 'إدارة مفاتيح API',
  },
  copyLabel: 'نسخ',
  copiedLabel: 'تم النسخ',
};

export function getAgentAiCopy(locale: Locale): AgentAiPageCopy {
  return locale === 'en' ? en : ar;
}
