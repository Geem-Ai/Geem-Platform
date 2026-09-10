import type { Locale } from '../lib/i18n';

export type UseCaseId =
  | 'customer'
  | 'employee'
  | 'operations'
  | 'sales'
  | 'finance'
  | 'it'
  | 'research'
  | 'arabic'
  | 'developer'
  | 'devices'
  | 'municipal'
  | 'visitor';

export type UseCase = {
  id: UseCaseId;
  label: string;
  channel: string;
  title: string;
  description: string;
  challenge: string;
  outcome: string;
  question: string;
  imageAlt: string;
  steps: { label: string; description: string }[];
  related: string[];
  proposed?: true;
};

export type UseCasesCopy = {
  eyebrow: string;
  title: string;
  description: string;
  tabsLabel: string;
  exampleLabel: string;
  requestLabel: string;
  flowLabel: string;
  challengeLabel: string;
  outcomeLabel: string;
  relatedLabel: string;
  proposedLabel: string;
  selectionLabel: string;
  note: string;
  cases: UseCase[];
};

const en: UseCasesCopy = {
  "eyebrow": "GEEM at work",
  "title": "From a business need to a practical workflow",
  "description": "Explore how GEEM helps teams draft, investigate, serve and act. Each example connects a real work challenge with the knowledge, systems and review needed to move it forward.",
  "tabsLabel": "Choose a practical use case",
  "exampleLabel": "Illustrative workflow",
  "requestLabel": "Example starting point",
  "flowLabel": "How the work moves forward",
  "challengeLabel": "The challenge",
  "outcomeLabel": "Practical value",
  "relatedLabel": "More ways to apply it",
  "proposedLabel": "Proposed application",
  "selectionLabel": "Choose a use case",
  "note": "These workflows illustrate how GEEM can be configured. Connected actions require integrations, permissions and appropriate approvals; your application or connected service executes them. Experts report returned results. People review drafts, extracted text and technical recommendations before use. Predictive municipal compliance is proposed for evaluation with specialists; official decisions remain with the responsible authority.",
  "cases": [
    {
      "id": "customer",
      "label": "Customer service",
      "channel": "Website · WhatsApp",
      "title": "Turn a delivery question into a tracked request",
      "description": "Connect delivery policies with current order details so GEEM can explain available options, prepare a date change and keep the customer informed of the result returned by your system.",
      "challenge": "Customers need delivery changes, while service teams navigate policies, order details and separate systems.",
      "outcome": "Customers receive a clear next step and a confirmed status their service team can follow.",
      "question": "Can I change the delivery date for my order?",
      "imageAlt": "A male shop owner using a phone and laptop in his store.",
      "steps": [
        {
          "label": "Understand the request",
          "description": "Identify the order, preferred date and relevant delivery policy."
        },
        {
          "label": "Explain the options",
          "description": "Explain the available choices and gather the details needed for a change."
        },
        {
          "label": "Submit the change",
          "description": "The connected system checks access and eligibility before submitting the request."
        },
        {
          "label": "Report the result",
          "description": "Share the confirmed update or explain the next available step."
        }
      ],
      "related": [
        "Return requests",
        "Warranty guidance",
        "Order follow-up"
      ]
    },
    {
      "id": "employee",
      "label": "Employee support",
      "channel": "Workspace chat · Internal apps",
      "title": "Guide leave requests from policy to approval",
      "description": "Use GEEM to explain leave requirements, collect the employee’s preferred dates and prepare a request. Connect your HR process so the employee can follow the reference and approval status.",
      "challenge": "Employees struggle to find leave requirements and track requests across policies, forms and approval channels.",
      "outcome": "Employees prepare informed requests and see progress, while managers retain their existing approval responsibilities.",
      "question": "How can I request annual leave for next month?",
      "imageAlt": "Three male colleagues reviewing information together in an office.",
      "steps": [
        {
          "label": "Explain the policy",
          "description": "Find the leave requirements relevant to the employee’s request."
        },
        {
          "label": "Prepare the request",
          "description": "Gather preferred dates and any details required by the leave policy."
        },
        {
          "label": "Submit for approval",
          "description": "The HR system checks permissions and sends the request through its approval process."
        },
        {
          "label": "Track progress",
          "description": "Return the request reference and the approval status received from the system."
        }
      ],
      "related": [
        "Onboarding guidance",
        "Policy explanations",
        "Employee service requests"
      ]
    },
    {
      "id": "operations",
      "label": "Operations",
      "channel": "Business apps · Workspace chat",
      "title": "Find the next step for a delayed shipment",
      "description": "Combine shipping procedures with current system information. GEEM helps the team identify a delayed shipment, understand its reported status and prepare the appropriate follow-up using the relevant operating procedure.",
      "challenge": "A delayed shipment requires staff to reconcile tracking updates with procedures before coordinating the response.",
      "outcome": "The team receives shipment context and a relevant procedure to guide a consistent follow-up.",
      "question": "This shipment is delayed. What should I do next?",
      "imageAlt": "Two male warehouse workers wearing hard hats and safety vests.",
      "steps": [
        {
          "label": "Identify the shipment",
          "description": "Gather the shipment reference and the details of the reported delay."
        },
        {
          "label": "Retrieve current status",
          "description": "The connected system checks access and returns the latest shipment information."
        },
        {
          "label": "Connect the procedure",
          "description": "Relate the returned status to the relevant shipping instructions."
        },
        {
          "label": "Prepare the next step",
          "description": "Explain the follow-up procedure and any information the operations team still needs."
        }
      ],
      "related": [
        "Delivery exceptions",
        "Warehouse procedures",
        "Supplier follow-up"
      ]
    },
    {
      "id": "sales",
      "label": "Sales",
      "channel": "Workspace chat · Sales apps",
      "title": "Build a proposal draft from the customer’s needs",
      "description": "Bring the customer brief, approved catalogue and permitted CRM details together. GEEM prepares a structured proposal draft so the sales team can check the scope, refine the offer and send it.",
      "challenge": "Sales teams assemble customer context, product information and proposal wording from several sources for each opportunity.",
      "outcome": "The team starts with a structured draft and can focus its review on the customer’s needs.",
      "question": "Prepare a proposal draft for this customer.",
      "imageAlt": "Two male business colleagues working together on a sales proposal.",
      "steps": [
        {
          "label": "Clarify the brief",
          "description": "Identify the customer’s requirements and the proposed scope of work."
        },
        {
          "label": "Use the catalogue",
          "description": "Select relevant information from the approved product and service catalogue."
        },
        {
          "label": "Retrieve customer context",
          "description": "The CRM integration returns the customer information the salesperson can access."
        },
        {
          "label": "Draft for review",
          "description": "Prepare a proposal for the salesperson to check, refine and send."
        }
      ],
      "related": [
        "Meeting briefs",
        "Product comparisons",
        "Follow-up drafts"
      ]
    },
    {
      "id": "finance",
      "label": "Finance",
      "channel": "Workspace chat · Finance apps",
      "title": "Prepare an expense claim the finance team can review",
      "description": "Guide employees through the expense policy and required evidence. GEEM helps prepare a business travel claim, submits it through the connected review process and reports its status without initiating payment.",
      "challenge": "Unclear expense rules and missing supporting documents lead to repeated clarification before finance can review claims.",
      "outcome": "Employees know what to provide, and finance receives a documented claim ready for its review.",
      "question": "How do I claim this business travel expense?",
      "imageAlt": "A male accountant reviewing financial documents at his desk.",
      "steps": [
        {
          "label": "Explain the requirements",
          "description": "Use the expense policy to explain the rules for this business travel claim."
        },
        {
          "label": "Gather supporting details",
          "description": "Collect the claim information and identify the required supporting documents."
        },
        {
          "label": "Send for review",
          "description": "The finance system checks permissions and submits the claim to its review process."
        },
        {
          "label": "Return the status",
          "description": "Show the claim reference and review status. No payment is initiated."
        }
      ],
      "related": [
        "Expense policy guidance",
        "Document checklists",
        "Claim follow-up"
      ]
    },
    {
      "id": "it",
      "label": "IT support",
      "channel": "Workspace chat · Internal apps",
      "title": "Give application access requests a clear route",
      "description": "Help employees understand application access requirements and prepare the right request. GEEM connects guidance with your existing approval process, then reports progress while access decisions remain with the designated approvers.",
      "challenge": "Employees need application access but may not know the required details, request route or approver.",
      "outcome": "IT receives a prepared request, and the employee can follow its status through the approval process.",
      "question": "How do I request access to a work application?",
      "imageAlt": "A male IT technician working beside server racks.",
      "steps": [
        {
          "label": "Identify the application",
          "description": "Gather the application name, work purpose and the access being requested."
        },
        {
          "label": "Explain the requirements",
          "description": "Use the relevant IT guidance to identify the details needed for the request."
        },
        {
          "label": "Route for approval",
          "description": "The connected system creates the request within the configured approval process."
        },
        {
          "label": "Report progress",
          "description": "Return the request status; granting access requires the designated approval."
        }
      ],
      "related": [
        "Troubleshooting guidance",
        "Equipment requests",
        "Support ticket preparation"
      ]
    },
    {
      "id": "research",
      "label": "Research & museums",
      "channel": "Documents · Knowledge collections",
      "title": "Turn printed and handwritten records into reviewed knowledge",
      "description": "GEEM uses OCR for printed text and HTR for handwriting to help research centres and museums digitize records. Specialists review and correct the extracted text before organizing it into usable knowledge.",
      "challenge": "Printed records and handwritten collections take substantial manual work to transcribe, review and organize for research.",
      "outcome": "Researchers work with reviewed digital text that can be organized, referenced and used by Experts.",
      "question": "Transcribe these documents so our team can review and organize them.",
      "imageAlt": "A male researcher working with a document scanner in a museum archive.",
      "steps": [
        {
          "label": "Prepare the sources",
          "description": "Provide scans of printed documents and handwritten records for extraction."
        },
        {
          "label": "Extract the text",
          "description": "GEEM applies OCR to printed text and HTR to handwriting."
        },
        {
          "label": "Review against the original",
          "description": "A researcher or curator checks the transcription and corrects recognition errors."
        },
        {
          "label": "Build the collection",
          "description": "Organize reviewed text into a knowledge collection for research and reference."
        }
      ],
      "related": [
        "Archive digitization",
        "Manuscript transcription",
        "Collection reference support"
      ]
    },
    {
      "id": "arabic",
      "label": "Arabic business writing",
      "channel": "Workspace chat · Business documents",
      "title": "Turn working notes into clear Arabic business writing",
      "description": "Give GEEM your key points, audience and terminology. It helps prepare formal Arabic or bilingual business drafts that your team can refine, check against the source and approve before sharing.",
      "challenge": "Teams need clear Arabic business communication while preserving meaning and terminology across drafts and languages.",
      "outcome": "Your team receives an editable draft with a clear structure and terminology to review before sharing.",
      "question": "Turn these notes into a formal Arabic letter and an English version.",
      "imageAlt": "Business colleagues reviewing a document together in an office.",
      "steps": [
        {
          "label": "Set the purpose",
          "description": "Provide the audience, intended message, source material and preferred terminology."
        },
        {
          "label": "Structure the message",
          "description": "Organize the supplied points into a suitable business format."
        },
        {
          "label": "Prepare the draft",
          "description": "Draft formal Arabic or paired Arabic and English wording from the supplied context."
        },
        {
          "label": "Review before sharing",
          "description": "The team checks facts, meaning, tone and terminology, then approves the final wording."
        }
      ],
      "related": [
        "Formal correspondence",
        "Executive summaries",
        "Bilingual presentations"
      ]
    },
    {
      "id": "developer",
      "label": "Developer assistance",
      "channel": "Workspace chat · API documentation",
      "title": "Move from an integration requirement to a reviewable draft",
      "description": "Share an API specification, a code excerpt and the intended workflow with GEEM. Get an implementation outline, draft code and test ideas for your developers to review and validate in their environment.",
      "challenge": "Developers translate API documentation and business requirements into integration logic, error handling and meaningful tests.",
      "outcome": "Developers get a concrete starting point for implementation while retaining control over validation and deployment.",
      "question": "Draft an API integration for this workflow, including error handling and test cases.",
      "imageAlt": "A developer reviewing technical information on a laptop.",
      "steps": [
        {
          "label": "Define the integration",
          "description": "Provide the API documentation, inputs, expected outputs and relevant code context."
        },
        {
          "label": "Outline the workflow",
          "description": "Describe the request flow, error cases and assumptions that need checking."
        },
        {
          "label": "Draft code and tests",
          "description": "Prepare implementation examples and test cases for the development team."
        },
        {
          "label": "Validate with the team",
          "description": "Developers review the draft, run tests in their environment and manage the release through their own process."
        }
      ],
      "related": [
        "API documentation drafts",
        "Code explanations",
        "Error analysis"
      ]
    },
    {
      "id": "devices",
      "label": "Connected devices",
      "channel": "IoT · Cameras · Maintenance systems",
      "title": "Turn a device alert into a maintenance case for review",
      "description": "GEEM integrates with IoT devices and cameras. Connect an alert from configured rules with site information and maintenance procedures so a technician can verify the condition and prepare the appropriate follow-up.",
      "challenge": "Device alerts arrive without the site context or procedure staff need to decide the next step.",
      "outcome": "Maintenance staff receive a contextualized case to verify and route through their existing work process.",
      "question": "A configured device rule raised an alert at this site. Prepare it for maintenance review.",
      "imageAlt": "A facilities manager and maintenance engineer reviewing a tablet.",
      "steps": [
        {
          "label": "Receive the alert",
          "description": "Use an alert from configured rules, with its device, location and observation time."
        },
        {
          "label": "Add operational context",
          "description": "Relate the available reading or camera observation to site information and maintenance guidance."
        },
        {
          "label": "Verify the condition",
          "description": "A technician checks the evidence and decides whether maintenance follow-up is required."
        },
        {
          "label": "Prepare maintenance follow-up",
          "description": "Create a maintenance request through the connected service after technician review, with the evidence needed for follow-up."
        }
      ],
      "related": [
        "Temperature alerts",
        "Equipment observations",
        "Facility condition reviews"
      ]
    },
    {
      "id": "municipal",
      "label": "Preventive compliance",
      "channel": "Device signals · Requirements · Specialist review",
      "title": "Assess compliance risks before a condition escalates",
      "description": "Explore a proposed workflow that relates device or camera signals to municipal requirements. GEEM would explain potential risks and supporting evidence so specialists can assess the case and coordinate an appropriate response.",
      "challenge": "Field indicators and service schedules can remain disconnected until a developing condition requires attention from specialists.",
      "outcome": "A reviewable risk assessment would help specialists consider earlier action, with official decisions remaining with the authority.",
      "question": "Assess waste-container fill indicators against the collection schedule and explain the potential risk.",
      "imageAlt": "A municipal employee and a resident reviewing a tablet in a city street.",
      "steps": [
        {
          "label": "Read the indicators",
          "description": "Gather permitted device readings or camera observations, location and update time."
        },
        {
          "label": "Connect requirements and context",
          "description": "Relate the indicators to applicable requirements, configured thresholds and service schedules."
        },
        {
          "label": "Explain the potential risk",
          "description": "Prepare an assessment with reasons and supporting evidence, including what still needs verification."
        },
        {
          "label": "Refer for specialist review",
          "description": "Specialists verify the case and coordinate any authorized handoff; the authority retains official classification and decisions."
        }
      ],
      "related": [
        "Food temperature risks",
        "Waste collection planning",
        "Recurring pavement obstruction"
      ],
      "proposed": true
    },
    {
      "id": "visitor",
      "label": "Visitor & guest services",
      "channel": "Website · WhatsApp · Destination systems",
      "title": "Connect destination guidance with a guest’s next request",
      "description": "Use current destination information and service policies to help visitors plan their visit. GEEM can explain available options, prepare a guest service request through configured channels and report the system’s response.",
      "challenge": "Visitors need current information and a clear service route across destination guides, channels and operating teams.",
      "outcome": "Visitors receive relevant guidance and a traceable request status, while service teams handle the follow-up.",
      "question": "What can I visit today, and how can I request assistance at the visitor centre?",
      "imageAlt": "A guide helping a visitor at a tourism information centre.",
      "steps": [
        {
          "label": "Check the visit context",
          "description": "Identify the visitor’s destination, timing and needs, then use the current destination information."
        },
        {
          "label": "Explain available options",
          "description": "Share activities, opening times and site guidelines from the relevant sources."
        },
        {
          "label": "Prepare the service request",
          "description": "Gather the needed details and route the request through a configured destination system."
        },
        {
          "label": "Report the next step",
          "description": "Return the available request status and explain any follow-up required from the service team."
        }
      ],
      "related": [
        "Hotel service requests",
        "Event information",
        "Site visit guidelines"
      ]
    }
  ]
};

const ar: UseCasesCopy = {
  "eyebrow": "GEEM في أعمالك",
  "title": "من احتياج العمل إلى خطوات قابلة للتنفيذ",
  "description": "اكتشف كيف يساعد GEEM فرقك على إعداد المحتوى وتحليل الحالات وتقديم الخدمات ومتابعة الإجراءات. يربط كل مثال تحديًا عمليًا بالمعرفة والأنظمة والمراجعة اللازمة لمعالجته.",
  "tabsLabel": "اختر استخدامًا عمليًا",
  "exampleLabel": "مسار عمل توضيحي",
  "requestLabel": "مثال لنقطة البداية",
  "flowLabel": "كيف يتقدم العمل",
  "challengeLabel": "التحدي",
  "outcomeLabel": "القيمة العملية",
  "relatedLabel": "تطبيقات أخرى",
  "proposedLabel": "تطبيق مقترح",
  "selectionLabel": "اختر الاستخدام",
  "note": "توضّح هذه المسارات كيف يمكن تهيئة GEEM. تتطلب الإجراءات المتصلة تكاملات وصلاحيات وموافقات مناسبة، وينفّذها تطبيقك أو الخدمة المتصلة. ويعرض الخبراء النتائج الواردة. يراجع المختصون المسودات والنصوص المستخرجة والتوصيات التقنية قبل استخدامها. أما الامتثال البلدي الاستباقي فهو تطبيق مقترح للتقييم مع المختصين، وتبقى القرارات الرسمية لدى الجهة المختصة.",
  "cases": [
    {
      "id": "customer",
      "label": "خدمة العملاء",
      "channel": "الموقع الإلكتروني · WhatsApp",
      "title": "من استفسار عن التوصيل إلى طلب يمكن متابعته",
      "description": "اربط سياسات التوصيل ببيانات الطلب الحالية ليشرح GEEM الخيارات المتاحة، ويجهّز طلب تغيير الموعد، ويطلع العميل على النتيجة الواردة من نظامك وما يلزم لمتابعة طلبه مع فريق الخدمة.",
      "challenge": "يحتاج العميل إلى تعديل موعد التوصيل، بينما يتنقل فريق الخدمة بين السياسات وبيانات الطلب والأنظمة.",
      "outcome": "يحصل العميل على خطوة تالية واضحة وحالة مؤكدة يستطيع فريق الخدمة متابعة الطلب بناءً عليها.",
      "question": "هل يمكنني تغيير موعد توصيل طلبي؟",
      "imageAlt": "صاحب متجر يستخدم هاتفًا وحاسوبًا محمولًا داخل متجره.",
      "steps": [
        {
          "label": "فهم الطلب",
          "description": "تحديد الطلب والموعد المفضل وسياسة التوصيل ذات الصلة."
        },
        {
          "label": "توضيح الخيارات",
          "description": "شرح الخيارات المتاحة وجمع التفاصيل اللازمة لطلب التعديل."
        },
        {
          "label": "إرسال طلب التعديل",
          "description": "يتحقق النظام المتصل من الصلاحيات واستيفاء الشروط قبل إرسال الطلب."
        },
        {
          "label": "عرض النتيجة",
          "description": "عرض التحديث الذي أكّده النظام أو توضيح الخطوة التالية المتاحة."
        }
      ],
      "related": [
        "طلبات الاسترجاع",
        "إرشادات الضمان",
        "متابعة الطلبات"
      ]
    },
    {
      "id": "employee",
      "label": "دعم الموظفين",
      "channel": "محادثة مساحة العمل · التطبيقات الداخلية",
      "title": "طلب الإجازة من فهم السياسة إلى متابعة الموافقة",
      "description": "استعن بـ GEEM لشرح متطلبات الإجازة وجمع التواريخ التي يفضلها الموظف وتجهيز طلبه. اربط مسار الموارد البشرية ليتمكن الموظف من متابعة رقم الطلب وحالة الموافقة من النظام.",
      "challenge": "يواجه الموظفون صعوبة في معرفة متطلبات الإجازة ومتابعة الطلب بين السياسات والنماذج وقنوات الموافقة المختلفة.",
      "outcome": "يجهّز الموظف طلبه على أساس واضح ويتابع تقدمه، مع بقاء مسؤولية الموافقة لدى المديرين المختصين.",
      "question": "كيف أقدّم طلب إجازة سنوية للشهر القادم؟",
      "imageAlt": "ثلاثة زملاء رجال يراجعون المعلومات معًا في مكتب.",
      "steps": [
        {
          "label": "شرح السياسة",
          "description": "تحديد متطلبات الإجازة ذات الصلة بطلب الموظف."
        },
        {
          "label": "تجهيز الطلب",
          "description": "جمع التواريخ المفضلة والتفاصيل التي تتطلبها سياسة الإجازات."
        },
        {
          "label": "الإرسال للموافقة",
          "description": "يتحقق نظام الموارد البشرية من الصلاحيات ويرسل الطلب ضمن مسار الموافقات."
        },
        {
          "label": "متابعة التقدم",
          "description": "عرض رقم الطلب وحالة الموافقة الواردة من النظام."
        }
      ],
      "related": [
        "إرشادات الموظفين الجدد",
        "شرح السياسات",
        "طلبات خدمات الموظفين"
      ]
    },
    {
      "id": "operations",
      "label": "العمليات",
      "channel": "تطبيقات الأعمال · محادثة مساحة العمل",
      "title": "حدّد الخطوة التالية لشحنة متأخرة",
      "description": "اجمع إجراءات الشحن مع بيانات النظام الحالية. يساعد GEEM الفريق على تحديد الشحنة المتأخرة وفهم حالتها الواردة من النظام، ثم تحديد المتابعة المناسبة استنادًا إلى إجراء التشغيل ذي الصلة.",
      "challenge": "يتطلب تأخر الشحنة ربط تحديثات التتبع بإجراءات العمل قبل أن يتمكن الفريق من تنسيق الاستجابة.",
      "outcome": "يحصل الفريق على معلومات الشحنة والإجراء المرتبط بها لتوجيه المتابعة وفق خطوات واضحة ومتسقة.",
      "question": "تأخرت هذه الشحنة، ما الخطوة التالية؟",
      "imageAlt": "عاملان في مستودع يرتديان خوذات وسترات سلامة.",
      "steps": [
        {
          "label": "تحديد الشحنة",
          "description": "جمع رقم الشحنة وتفاصيل التأخر المبلّغ عنه."
        },
        {
          "label": "استرجاع الحالة الحالية",
          "description": "يتحقق النظام المتصل من الصلاحيات ويعيد أحدث معلومات الشحنة."
        },
        {
          "label": "ربط الإجراء المناسب",
          "description": "ربط الحالة الواردة بتعليمات الشحن ذات الصلة."
        },
        {
          "label": "تحديد الخطوة التالية",
          "description": "شرح إجراء المتابعة والمعلومات التي ما زال فريق العمليات يحتاج إليها."
        }
      ],
      "related": [
        "مشكلات التوصيل",
        "إجراءات المستودعات",
        "متابعة الموردين"
      ]
    },
    {
      "id": "sales",
      "label": "المبيعات",
      "channel": "محادثة مساحة العمل · تطبيقات المبيعات",
      "title": "ابنِ مسودة العرض على احتياج العميل",
      "description": "اجمع احتياج العميل ودليل المنتجات والخدمات المعتمد وبيانات CRM المتاحة للفريق. يجهّز GEEM مسودة عرض منظّمة ليراجع فريق المبيعات نطاقها، ويطوّر العرض ثم يرسله إلى العميل بعد اعتماده.",
      "challenge": "يجمع فريق المبيعات معلومات العميل والمنتجات وصياغة العرض من مصادر متعددة عند العمل على كل فرصة.",
      "outcome": "يبدأ الفريق بمسودة منظّمة تساعده على تركيز المراجعة على احتياجات العميل ونطاق العرض المقدم له.",
      "question": "جهّز مسودة عرض لهذا العميل.",
      "imageAlt": "زميلان في العمل يجهّزان عرضًا لعميل.",
      "steps": [
        {
          "label": "توضيح الاحتياج",
          "description": "تحديد متطلبات العميل ونطاق العمل المقترح."
        },
        {
          "label": "الاستفادة من الدليل",
          "description": "اختيار المعلومات ذات الصلة من دليل المنتجات والخدمات المعتمد."
        },
        {
          "label": "استرجاع معلومات العميل",
          "description": "يعيد تكامل CRM بيانات العميل التي يملك مسؤول المبيعات صلاحية الوصول إليها."
        },
        {
          "label": "إعداد مسودة للمراجعة",
          "description": "تجهيز عرض يراجعه مسؤول المبيعات ويعدّله ثم يرسله."
        }
      ],
      "related": [
        "ملخصات الاجتماعات",
        "مقارنة المنتجات",
        "مسودات رسائل المتابعة"
      ]
    },
    {
      "id": "finance",
      "label": "المالية",
      "channel": "محادثة مساحة العمل · التطبيقات المالية",
      "title": "جهّز مطالبة مصروفات واضحة للفريق المالي",
      "description": "أرشد الموظفين إلى سياسة المصروفات والمستندات المطلوبة. يساعد GEEM على تجهيز مطالبة بمصروفات رحلة عمل وإرسالها عبر مسار المراجعة المتصل، ثم عرض حالتها دون بدء أي عملية دفع.",
      "challenge": "يؤدي غموض قواعد المصروفات ونقص المستندات المؤيدة إلى تكرار الاستفسارات قبل تمكّن الفريق المالي من المراجعة.",
      "outcome": "يعرف الموظف ما يجب تقديمه، ويتلقى الفريق المالي مطالبة موثقة جاهزة للمراجعة وفق إجراءاته المعتمدة.",
      "question": "كيف أقدّم مطالبة بمصروفات رحلة العمل؟",
      "imageAlt": "محاسب يراجع مستندات مالية على مكتبه.",
      "steps": [
        {
          "label": "شرح المتطلبات",
          "description": "توضيح الضوابط المتعلقة بمطالبة رحلة العمل بالاستناد إلى سياسة المصروفات."
        },
        {
          "label": "جمع التفاصيل المؤيدة",
          "description": "جمع بيانات المطالبة وتحديد المستندات المطلوبة لدعمها."
        },
        {
          "label": "الإرسال للمراجعة",
          "description": "يتحقق النظام المالي من الصلاحيات ويرسل المطالبة ضمن مسار المراجعة."
        },
        {
          "label": "عرض الحالة",
          "description": "عرض رقم المطالبة وحالة مراجعتها، دون بدء أي عملية دفع."
        }
      ],
      "related": [
        "شرح سياسة المصروفات",
        "قوائم المستندات المطلوبة",
        "متابعة المطالبات"
      ]
    },
    {
      "id": "it",
      "label": "الدعم التقني",
      "channel": "محادثة مساحة العمل · التطبيقات الداخلية",
      "title": "مسار واضح لطلب صلاحيات التطبيقات",
      "description": "ساعد الموظفين على فهم متطلبات استخدام التطبيقات وتجهيز الطلب المناسب. يربط GEEM الإرشادات بمسار الموافقات الحالي ويعرض تقدم الطلب، مع بقاء قرار منح الصلاحية لدى المسؤولين المحددين للموافقة.",
      "challenge": "يحتاج الموظفون إلى صلاحيات التطبيقات دون معرفة التفاصيل المطلوبة أو مسار الطلب أو المسؤول عن الموافقة.",
      "outcome": "يتلقى فريق التقنية طلبًا مجهّزًا، ويستطيع الموظف متابعة حالته ضمن مسار الموافقات المعتمد لدى المؤسسة.",
      "question": "كيف أطلب صلاحية استخدام أحد تطبيقات العمل؟",
      "imageAlt": "فني تقنية معلومات يعمل بجانب رفوف الخوادم.",
      "steps": [
        {
          "label": "تحديد التطبيق",
          "description": "جمع اسم التطبيق والغرض من استخدامه والصلاحية المطلوبة."
        },
        {
          "label": "شرح المتطلبات",
          "description": "تحديد المعلومات اللازمة للطلب بالاستناد إلى الإرشادات التقنية ذات الصلة."
        },
        {
          "label": "التوجيه للموافقة",
          "description": "ينشئ النظام المتصل الطلب ضمن مسار الموافقات الذي جرى إعداده."
        },
        {
          "label": "عرض التقدم",
          "description": "عرض حالة الطلب، مع اشتراط الموافقة المحددة قبل منح الصلاحية."
        }
      ],
      "related": [
        "إرشادات معالجة الأعطال",
        "طلبات الأجهزة",
        "تجهيز تذاكر الدعم"
      ]
    },
    {
      "id": "research",
      "label": "الأبحاث والمتاحف",
      "channel": "الوثائق · المجموعات المعرفية",
      "title": "من الوثائق والمخطوطات إلى معرفة رقمية بعد المراجعة",
      "description": "يستخدم GEEM تقنية OCR للنص المطبوع وHTR للخط اليدوي لمساعدة مراكز الأبحاث والمتاحف على رقمنة السجلات. يراجع المختصون النص المستخرج ويصحّحونه قبل تنظيمه ضمن معرفة قابلة للاستخدام.",
      "challenge": "تتطلب الوثائق المطبوعة والمجموعات المكتوبة بخط اليد جهدًا يدويًا كبيرًا لاستخراج نصوصها ومراجعتها وتنظيمها للبحث.",
      "outcome": "يعمل الباحثون على نص رقمي تمت مراجعته ويمكن تنظيمه والرجوع إليه والاستفادة منه عبر الخبراء.",
      "question": "استخرج نصوص هذه الوثائق ليتمكن فريقنا من مراجعتها وتنظيمها.",
      "imageAlt": "باحث يعمل على ماسح ضوئي للوثائق في أرشيف متحف.",
      "steps": [
        {
          "label": "تجهيز المصادر",
          "description": "توفير صور ممسوحة ضوئيًا للوثائق المطبوعة والسجلات المكتوبة بخط اليد."
        },
        {
          "label": "استخراج النص",
          "description": "يطبّق GEEM تقنية OCR على النص المطبوع وHTR على الخط اليدوي."
        },
        {
          "label": "المراجعة مقابل الأصل",
          "description": "يراجع الباحث أو أمين المتحف النص ويصحّح أخطاء التعرّف."
        },
        {
          "label": "بناء المجموعة المعرفية",
          "description": "تنظيم النص بعد مراجعته ضمن مجموعة معرفية للبحث والرجوع إليها."
        }
      ],
      "related": [
        "رقمنة الأرشيف",
        "استخراج نصوص المخطوطات",
        "إتاحة المجموعات للباحثين"
      ]
    },
    {
      "id": "arabic",
      "label": "الكتابة العربية للأعمال",
      "channel": "محادثة مساحة العمل · مستندات الأعمال",
      "title": "حوّل ملاحظات العمل إلى صياغة عربية واضحة",
      "description": "زوّد GEEM بالنقاط الأساسية والجمهور المستهدف والمصطلحات. يساعدك على إعداد مسودات أعمال بالعربية الرسمية أو باللغتين العربية والإنجليزية، ليطوّرها فريقك ويطابقها مع المصدر ويعتمدها قبل مشاركتها مع الآخرين.",
      "challenge": "تحتاج الفرق إلى تواصل مهني واضح بالعربية مع الحفاظ على المعنى والمصطلحات بين المسودات واللغات.",
      "outcome": "يحصل فريقك على مسودة قابلة للتعديل ذات بنية واضحة ومصطلحات يمكن مراجعتها قبل اعتمادها ومشاركتها.",
      "question": "حوّل هذه الملاحظات إلى خطاب رسمي بالعربية ونسخة باللغة الإنجليزية.",
      "imageAlt": "زملاء عمل يراجعون مستندًا معًا في مكتب.",
      "steps": [
        {
          "label": "تحديد الغرض",
          "description": "توفير الجمهور المستهدف والرسالة المطلوبة والمادة المرجعية والمصطلحات المفضلة."
        },
        {
          "label": "تنظيم الرسالة",
          "description": "ترتيب النقاط المقدّمة ضمن صيغة مناسبة لطبيعة العمل."
        },
        {
          "label": "إعداد المسودة",
          "description": "صياغة نص عربي رسمي أو نسختين عربية وإنجليزية استنادًا إلى المعلومات المقدّمة."
        },
        {
          "label": "المراجعة قبل المشاركة",
          "description": "يراجع الفريق الحقائق والمعنى والأسلوب والمصطلحات ثم يعتمد الصياغة النهائية."
        }
      ],
      "related": [
        "المراسلات الرسمية",
        "الملخصات التنفيذية",
        "العروض ثنائية اللغة"
      ]
    },
    {
      "id": "developer",
      "label": "مساعدة المطورين",
      "channel": "محادثة مساحة العمل · وثائق API",
      "title": "من متطلبات التكامل إلى مسودة قابلة للمراجعة",
      "description": "شارك مواصفات API ومقتطفًا برمجيًا ومسار العمل المطلوب مع GEEM. احصل على تصور للتنفيذ ومسودة شيفرة وأفكار للاختبارات، ليراجعها مطوروك ويتحققوا من ملاءمتها في بيئتهم قبل استخدامها الفعلي.",
      "challenge": "يحوّل المطورون وثائق API ومتطلبات الأعمال إلى منطق تكامل ومعالجة للأخطاء واختبارات تتحقق من السلوك المطلوب.",
      "outcome": "يحصل المطورون على نقطة بداية عملية للتنفيذ، مع احتفاظهم بمسؤولية مراجعة الشيفرة واختبارها والتحقق من جاهزيتها للإطلاق.",
      "question": "جهّز مسودة تكامل عبر API لهذا المسار، مع معالجة الأخطاء وحالات الاختبار.",
      "imageAlt": "مطور يراجع معلومات تقنية على حاسوب محمول.",
      "steps": [
        {
          "label": "تحديد التكامل",
          "description": "توفير وثائق API والمدخلات والمخرجات المتوقعة والشيفرة ذات الصلة."
        },
        {
          "label": "رسم مسار العمل",
          "description": "توضيح تسلسل الطلبات وحالات الخطأ والافتراضات التي تحتاج إلى تحقق."
        },
        {
          "label": "إعداد الشيفرة والاختبارات",
          "description": "تجهيز أمثلة للتنفيذ وحالات اختبار يراجعها فريق التطوير."
        },
        {
          "label": "التحقق لدى الفريق",
          "description": "يراجع المطورون المسودة، ويجرون الاختبارات في بيئتهم، ويديرون الإطلاق وفق إجراءاتهم."
        }
      ],
      "related": [
        "مسودات وثائق API",
        "شرح الشيفرة",
        "تحليل الأخطاء"
      ]
    },
    {
      "id": "devices",
      "label": "الأجهزة المتصلة",
      "channel": "إنترنت الأشياء · الكاميرات · أنظمة الصيانة",
      "title": "من تنبيه الجهاز إلى حالة صيانة جاهزة للمراجعة",
      "description": "يتكامل GEEM مع أجهزة إنترنت الأشياء والكاميرات. اربط التنبيه الناتج عن قواعد معدّة مسبقًا بمعلومات الموقع وإجراءات الصيانة، ليتحقق الفني من الحالة ويحدّد المتابعة المناسبة وفق إجراء العمل.",
      "challenge": "تصل تنبيهات الأجهزة دون معلومات الموقع أو الإجراء الذي يحتاجه الموظفون لتحديد الخطوة التالية المناسبة.",
      "outcome": "يتلقى فريق الصيانة حالة مدعومة بالسياق ليتحقق منها ويوجهها ضمن مسار العمل المعتمد لدى المؤسسة.",
      "question": "ورد تنبيه من جهاز متصل في هذا الموقع، جهّز الحالة لمراجعة فريق الصيانة.",
      "imageAlt": "مدير مرافق ومهندس صيانة يراجعان جهازًا لوحيًا.",
      "steps": [
        {
          "label": "استقبال التنبيه",
          "description": "البدء بتنبيه صادر عن قواعد معدّة، مع بيانات الجهاز والموقع ووقت الرصد."
        },
        {
          "label": "إضافة سياق التشغيل",
          "description": "ربط القراءة المتاحة أو ملاحظة الكاميرا بمعلومات الموقع وإرشادات الصيانة."
        },
        {
          "label": "التحقق من الحالة",
          "description": "يراجع الفني الأدلة ويحدّد ما إذا كانت الحالة تتطلب متابعة من الصيانة."
        },
        {
          "label": "إعداد طلب الصيانة",
          "description": "إنشاء طلب صيانة عبر الخدمة المتصلة بعد مراجعة الفني، مع إرفاق الأدلة اللازمة للمتابعة."
        }
      ],
      "related": [
        "تنبيهات درجات الحرارة",
        "ملاحظات حالة المعدات",
        "مراجعة حالة المرافق"
      ]
    },
    {
      "id": "municipal",
      "label": "الامتثال الاستباقي",
      "channel": "مؤشرات الأجهزة · الاشتراطات · مراجعة المختصين",
      "title": "تقدير مخاطر المخالفة قبل تفاقم الحالة",
      "description": "استكشف مسارًا مقترحًا يربط مؤشرات الأجهزة أو الكاميرات بالاشتراطات البلدية. يوضّح GEEM المخاطر المحتملة وأدلتها الداعمة لتمكين المختصين من تقييم الحالة وتنسيق الاستجابة المناسبة وفق مسؤوليات الجهة المختصة.",
      "challenge": "قد تبقى المؤشرات الميدانية وجداول الخدمة منفصلة حتى تتطور الحالة وتستدعي انتباه المختصين وتدخلهم لمعالجتها.",
      "outcome": "يساعد التقييم القابل للمراجعة المختصين على دراسة التدخل المبكر، مع بقاء القرارات الرسمية لدى الجهة المختصة.",
      "question": "قيّم مؤشرات امتلاء حاوية النفايات مقارنةً بجدول الجمع، ووضّح الخطر المحتمل.",
      "imageAlt": "موظف بلدي ومستفيد يراجعان جهازًا لوحيًا في أحد شوارع المدينة.",
      "steps": [
        {
          "label": "قراءة المؤشرات",
          "description": "جمع قراءات الأجهزة أو ملاحظات الكاميرات المسموح بها مع الموقع ووقت التحديث."
        },
        {
          "label": "ربط الاشتراطات بالسياق",
          "description": "ربط المؤشرات بالاشتراطات ذات الصلة والحدود المحددة وجداول تقديم الخدمة."
        },
        {
          "label": "توضيح الخطر المحتمل",
          "description": "إعداد تقييم يبيّن الأسباب والأدلة الداعمة وما يحتاج إلى تحقق إضافي."
        },
        {
          "label": "الإحالة لمراجعة المختصين",
          "description": "يتحقق المختصون من الحالة وينسّقون إحالتها وفق الصلاحيات؛ وتبقى قرارات تصنيف المخالفات والإجراءات الرسمية لدى الجهة المختصة."
        }
      ],
      "related": [
        "مخاطر درجات حرارة الأغذية",
        "تخطيط جمع النفايات",
        "تكرار إشغال الأرصفة"
      ],
      "proposed": true
    },
    {
      "id": "visitor",
      "label": "خدمات الزوار والضيوف",
      "channel": "الموقع الإلكتروني · WhatsApp · أنظمة الوجهة",
      "title": "من إرشاد الزائر إلى متابعة طلب الخدمة",
      "description": "استعن بمعلومات الوجهة الحالية وسياسات الخدمة لمساعدة الزوار على التخطيط لزيارتهم. يشرح GEEM الخيارات المتاحة ويجهّز طلب خدمة عبر القنوات التي جرى ربطها، ثم يعرض الرد الوارد من النظام.",
      "challenge": "يحتاج الزوار إلى معلومات حديثة ومسار خدمة واضح عبر أدلة الوجهة وقنواتها وفرق التشغيل المختلفة.",
      "outcome": "يحصل الزائر على إرشادات مناسبة وحالة طلب يمكن متابعتها، بينما يتولى فريق الخدمة استكمال الإجراء.",
      "question": "ما المواقع التي يمكنني زيارتها اليوم، وكيف أطلب المساعدة في مركز الزوار؟",
      "imageAlt": "مرشد يساعد زائرًا في مركز معلومات سياحي.",
      "steps": [
        {
          "label": "فهم سياق الزيارة",
          "description": "تحديد الوجهة والوقت واحتياج الزائر والرجوع إلى معلومات الوجهة الحالية."
        },
        {
          "label": "شرح الخيارات المتاحة",
          "description": "عرض الأنشطة وأوقات العمل وإرشادات زيارة المواقع من المصادر ذات الصلة."
        },
        {
          "label": "تجهيز طلب الخدمة",
          "description": "جمع التفاصيل اللازمة وتوجيه الطلب عبر أحد أنظمة الوجهة التي جرى ربطها."
        },
        {
          "label": "عرض الخطوة التالية",
          "description": "عرض حالة الطلب المتاحة وتوضيح المتابعة المطلوبة من فريق الخدمة."
        }
      ],
      "related": [
        "طلبات خدمات الفنادق",
        "معلومات الفعاليات",
        "إرشادات زيارة المواقع"
      ]
    }
  ]
};

export function getUseCasesCopy(locale: Locale): UseCasesCopy {
  return locale === 'en' ? en : ar;
}
