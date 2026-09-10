import type { SiteCopy } from './types';

export const en: SiteCopy = {
  meta: {
    homeTitle: 'GEEM | Business AI in the cloud or on your premises',
    homeDescription:
      'Use GEEM cloud or tailored infrastructure we provide at your site. Connect AI Experts to your knowledge and systems, with capacity planned around your business.',
    aboutTitle: 'About GEEM and DALSEEN',
    aboutDescription:
      'Meet GEEM, the AI product of DALSEEN—a Saudi technology company that began in Jeddah and is now based in Madinah.',
    contactTitle: 'Contact GEEM',
    contactDescription: 'Discuss GEEM cloud or client-site infrastructure, business integrations, capacity and operating costs with our team.',
    privacyTitle: 'Privacy Policy',
    privacyDescription: 'What GEEM processes, why it is needed, how organizations manage workspaces, and how you can exercise your rights.',
    termsTitle: 'Terms of Use',
    termsDescription: 'Terms for using GEEM workspaces, Experts, integrations, and the responsibilities of organizations and users.',
    pdplTitle: 'Personal Data Protection Notice',
    pdplDescription: 'Personal data protection notice for GEEM users.',
    securityTitle: 'Security and your organization’s privacy',
    securityDescription:
      'Explore GEEM workspace controls and review the operating environment, data flows and access requirements for cloud or client-site deployment.',
  },
  a11y: {
    skipToContent: 'Skip to content',
    openMenu: 'Open menu',
    closeMenu: 'Close menu',
    primaryNavigation: 'Primary navigation',
    mobileNavigation: 'Mobile navigation',
    languageSwitch: 'العربية',
  },
  brand: {
    product: 'GEEM',
    tagline: 'AI for everyday work and business',
  },
  nav: {
    items: [
      { id: 'product', label: 'Product', href: 'product' },
      { id: 'experts', label: 'Experts', href: 'experts' },
      { id: 'solutions', label: 'Solutions', href: 'use-cases' },
      { id: 'integrations', label: 'Integrations', href: 'integrations' },
      { id: 'api', label: 'Developers', href: 'api' },
      { id: 'security', label: 'Security', href: 'security' },
    ],
    primaryCta: 'Start with GEEM',
    login: 'Workspace Login',
  },
  hero: {
    eyebrow: 'GEEM AI · Built in Saudi Arabia',
    title: 'One AI experience',
    titleAccent: 'More ways to work',
    description:
      'Write, explore ideas and get help with code. Bring GEEM into your business through Experts connected to your knowledge, channels and systems. Choose GEEM cloud or client-site deployment, then expand from a practical need.',
    primaryCta: 'Start with GEEM',
    tertiaryCta: 'Explore the platform',
    foundationLine: 'Our fine-tuned AI · GEEM cloud or your premises',
  },
  valueStrip: {
    items: [
      {
        title: 'Everyday intelligence',
        description: 'Write, code and put business knowledge to work across reusable Experts and workflows.',
      },
      {
        title: 'Our own AI foundation',
        description: 'GEEM’s fine-tuned AI builds on multiple models and continues to evolve.',
      },
      {
        title: 'Cloud or your premises',
        description: 'Use GEEM cloud or infrastructure we tailor and provide at your site, with capacity planned for your workload.',
      },
    ],
  },
  experts: {
    number: '01',
    eyebrow: 'Make it work for your business',
    title: 'Give AI a role in your business',
    description:
      'Start with general AI, then create Experts for work that needs your business context. Give each Expert a purpose, instructions, selected knowledge and the connections it may use.',
    flowExpertLabel: 'GEEM Expert',
    formula: ['Purpose', 'Instructions', 'Business knowledge', 'Controlled access'],
    cards: [
      {
        title: 'HR Expert',
        description: 'Connects HR policies to employee service requests through your configured systems.',
      },
      {
        title: 'Finance Expert',
        description: 'Pairs expense policies with authorized lookups in your finance tools.',
      },
      {
        title: 'Operations Expert',
        description: 'Combines operating procedures with authorized lookups and requests in your tools.',
      },
    ],
    diagramCaption: 'Business knowledge → Expert → Channels & connected systems',
    note: 'Illustrative roles. Your organization defines its Experts and their permitted use.',
  },
  knowledge: {
    eyebrow: 'Approved knowledge',
    sources: ['PDF', 'Text & Markdown', 'Google Drive', 'Microsoft OneDrive'],
  },
  integrations: {
    number: '02',
    eyebrow: 'Apps & integrations',
    title: 'Bring your knowledge and connect your channels',
    description:
      'Upload documents or connect selected files from Google Drive and OneDrive. Then choose where people can reach your Experts.',
    items: [
      {
        id: 'google-drive',
        title: 'Google Drive',
        description: 'Knowledge source',
      },
      {
        id: 'microsoft-onedrive',
        title: 'Microsoft OneDrive',
        description: 'Knowledge source',
      },
      {
        id: 'whatsapp',
        title: 'WhatsApp',
        description: 'Conversation channel',
      },
      {
        id: 'chat-widget',
        title: 'Website chat',
        description: 'Website channel',
      },
    ],
    systemCard: {
      eyebrow: 'Business systems',
      title: 'Connect knowledge to action',
      description:
        'Your technical team can connect Experts to internal tools and business systems, so they can request permitted actions using relevant business knowledge. Your application or a connected service executes the action.',
      tags: ['Custom integrations', 'Internal tools', 'Permitted actions'],
    },
  },
  channels: {
    number: '03',
    eyebrow: 'Channels',
    title: 'One Expert, available where work happens',
    description:
      'Connect an Expert to the channels your team and customers use. Add configured tools where you want it to support actions as well as conversations.',
    nodes: [
      {
        id: 'chat',
        label: 'GEEM Chat',
        context: 'For your team',
        description: 'Ask the Expert in your workspace and trace answers to their sources.',
      },
      {
        id: 'api',
        label: 'API & systems',
        context: 'For your systems',
        description: 'Bring Expert answers and requests for authorized actions into your applications.',
      },
      {
        id: 'whatsapp',
        label: 'WhatsApp',
        context: 'For customers and teams',
        description: 'Make the selected Expert available in WhatsApp conversations.',
      },
      {
        id: 'widget',
        label: 'Website chat',
        context: 'For website visitors',
        description: 'Embed a branded chat widget connected to one Expert.',
      },
    ],
  },
  api: {
    number: '04',
    eyebrow: 'Connect your business systems',
    title: 'Put AI to work in your applications',
    description:
      'Your technical team connects the Expert to the systems that run your business. Choose how actions are executed, with the required integrations, access and permissions in place.',
    points: [
      'Choose which Expert your application uses',
      'Control and revoke access keys',
      'Review usage from your workspace',
    ],
    paths: [
      {
        title: 'Client Agent API',
        description: 'The Expert requests an action. Your application checks authorization, executes it and sends the result back to GEEM.',
      },
      {
        title: 'MCP Connectors',
        description: 'GEEM coordinates calls to tools you have granted access to. The connected service executes the action, subject to configured permissions and approvals.',
      },
    ],
    docsLabel: 'Explore the Agent API documentation',
  },
  security: {
    number: '05',
    eyebrow: 'Trust & privacy',
    title: 'Clear boundaries for your organization’s knowledge',
    description:
      'Access is separated by workspace and enforced by the backend. Your organization controls members, roles, sources, integrations, and API keys.',
    points: [
      {
        title: 'Workspace separation',
        description: 'Knowledge access and retrieval are scoped to the workspace and Expert.',
      },
      {
        title: 'Role-based access',
        description: 'Workspace roles control what members can manage and use.',
      },
      {
        title: 'Protected credentials',
        description: 'Integration credentials are encrypted, while API keys are scoped and revocable.',
      },
    ],
    linkLabel: 'Read more about security',
    page: {
      hero: {
        eyebrow: 'Security & privacy at GEEM',
        title: 'Clear boundaries for your organization’s knowledge',
        description:
          'GEEM provides workspace isolation and server-enforced permissions. Review these controls alongside your cloud or client-site operating environment and connected systems.',
        primaryCta: 'Discuss your requirements',
        secondaryCta: 'Explore the controls',
      },
      boundary: {
        label: 'Workspace boundary',
        title: 'Your organization’s space',
        caption:
          'Each request passes through workspace context and user permissions before it reaches the Expert and authorized knowledge.',
        items: [
          { id: 'knowledge', label: 'Sources you approve' },
          { id: 'permissions', label: 'Role-based permissions' },
          { id: 'credentials', label: 'Revocable keys' },
          { id: 'residency', label: 'Cloud data storage' },
        ],
      },
      facts: [
        { value: 'In Saudi Arabia', label: 'GEEM cloud core data' },
        { value: 'Logically isolated', label: 'Each organization’s knowledge' },
        { value: 'Server enforced', label: 'Roles and permissions' },
      ],
      controls: {
        eyebrow: 'Core safeguards',
        title: 'Protection starts before an answer is returned',
        description:
          'Controls work in connected layers, from resolving the workspace and member to scoping the Expert and the sources it may use.',
        items: [
          {
            id: 'workspace',
            title: 'Workspace isolation',
            description:
              'Queries, files, and knowledge indexes are separated by workspace, and retrieval is scoped to the authorized Expert.',
          },
          {
            id: 'roles',
            title: 'Server-enforced permissions',
            description:
              'Roles define what members can use or manage; protection does not depend on hiding interface controls.',
          },
          {
            id: 'integrations',
            title: 'Protected integration data',
            description:
              'App connection secrets are encrypted before storage and credentials are excluded from API responses.',
          },
          {
            id: 'access',
            title: 'Controllable sessions and keys',
            description:
              'Passwords are stored as secure hashes, sessions can be rotated or revoked, and API keys are workspace-bound and scoped.',
          },
        ],
      },
      requestFlow: {
        eyebrow: 'Request path',
        title: 'Four gates before knowledge is reached',
        description:
          'Protection does not rely on the visible interface; the platform rechecks context and authorization for every protected request.',
        steps: [
          'Resolve the workspace',
          'Verify membership and permission',
          'Scope the Expert and sources',
          'Return the answer and sources',
        ],
      },
      governance: {
        eyebrow: 'Shared responsibility',
        title: 'GEEM provides the controls and your organization decides who can reach what',
        description:
          'Access and knowledge remain deliberate choices for your organization, while GEEM enforces the technical boundaries inside the platform.',
        geemTitle: 'What GEEM protects',
        geemItems: [
          'Workspace data separation',
          'Permissions enforced in the platform',
          'Encrypted application connection secrets',
          'Scoped and revocable API keys',
        ],
        organizationTitle: 'What your organization controls',
        organizationItems: [
          'Members and their assigned roles',
          'Approved documents and sources',
          'Enabled applications and channels',
          'Human review before consequential decisions',
        ],
      },
      transparency: {
        eyebrow: 'Clarity before badges',
        title: 'Clear controls, accurately described',
        description:
          'GEEM cloud stores core workspace data in Saudi Arabia. Client-site storage and processing arrangements follow the agreed deployment scope. Some AI features and external integrations may require processing by service providers under the agreement and Privacy Policy.',
        note:
          'Before contracting, your team can review the operating environment, data flows and processing scope. We do not display certifications or compliance levels that have not been verified.',
      },
      cta: {
        title: 'Does your team have specific security requirements?',
        description: 'Review the deployment environment, data flows, permissions and operating responsibilities with our team before launch.',
        primaryCta: 'Contact the GEEM team',
        privacyCta: 'Privacy Policy',
        pdplCta: 'Data Protection Notice',
      },
    },
  },
  finalCta: {
    title: 'Start with the work you want to improve',
    description:
      'Write, explore and build with GEEM. For your organization, start with one workflow, connect its knowledge and systems, then reuse that foundation across teams and channels. Choose the cloud or client-site operating environment that fits your needs.',
    primaryCta: 'Start with GEEM',
    secondaryCta: 'Discuss your use case',
  },
  footer: {
    by: 'by',
    ownership: 'AI developed and operated by DALSEEN',
    visitCompany: 'Discover DALSEEN',
    contactLabel: 'Let’s talk',
    whatsapp: 'WhatsApp',
    companyDetails: 'The company behind GEEM',
    vatLabel: 'VAT number',
    unifiedNumberLabel: 'Unified national number',
    nationalAddressLabel: 'Short national address',
    geemPolicies: 'GEEM policies',
    socialLabel: 'Follow DALSEEN',
    backToTop: 'Back to top',
    product: 'Product',
    resources: 'Resources',
    company: 'Company',
    legal: 'Legal',
    productLinks: [
      { label: 'Platform', href: 'product' },
      { label: 'Experts', href: 'experts' },
      { label: 'Solutions', href: 'use-cases' },
      { label: 'Robotics · In development', href: 'robotics' },
      { label: 'Integrations', href: 'integrations' },
      { label: 'Developers', href: 'api' },
      { label: 'Workspace Login', href: 'login' },
    ],
    resourceLinks: [
      { label: 'Client Agent API', href: 'agent-ai' },
      { label: 'Security', href: 'security' },
      { label: 'Deployment options', href: 'deployment' },
      { label: 'Compare platforms', href: 'compare' },
    ],
    companyLinks: [
      { label: 'About DALSEEN', href: 'about' },
      { label: 'Contact', href: 'contact' },
      { label: 'DALSEEN Platform policies', href: 'dalseen-legal' },
    ],
    legalLinks: [
      { label: 'Privacy', href: 'privacy' },
      { label: 'Terms', href: 'terms' },
      { label: 'Data protection', href: 'pdpl' },
    ],
    rights: 'DALSEEN. All rights reserved.',
    madeIn: 'Made in Madinah',
  },
  about: {
    hero: {
      eyebrow: 'About GEEM',
      title: 'From Madinah, we build AI around how organizations really work',
      description:
        'GEEM is the AI product of Dal Seen Information Technology Company—a Saudi technology company that began in Jeddah and is now based in Madinah.',
      primaryCta: 'See how GEEM works',
      secondaryCta: 'Talk with the team',
      companyLabel: 'Saudi technology company',
      productLabel: 'AI for people and organizations',
    },
    facts: [
      { value: 'DALSEEN', label: 'The Saudi company building GEEM' },
      { value: 'Jeddah', label: 'Where the company journey began' },
      { value: 'Madinah', label: 'Where we build and grow today' },
    ],
    story: {
      eyebrow: 'Our story',
      title: 'We started with a practical need and grew alongside Saudi organizations',
      description:
        'DALSEEN began as a small team building digital solutions around real operating needs. As its work expanded across the Kingdom, it continued developing products that make technology clearer and more useful in the working day.',
      milestones: [
        {
          place: 'Jeddah',
          title: 'Starting with real work',
          description: 'The journey began during the pandemic by building digital solutions for practical operating needs.',
        },
        {
          place: 'Across Saudi Arabia',
          title: 'Growing with organizations',
          description: 'Experience expanded across Saudi markets, and the products evolved with what the team learned from customers.',
        },
        {
          place: 'Madinah',
          title: 'A home for long-term building',
          description: 'DALSEEN made Madinah its home base and continues to develop GEEM and its technology products from there.',
        },
      ],
    },
    principles: {
      eyebrow: 'How we build',
      title: 'Three principles connect DALSEEN and GEEM',
      description: 'We measure technology by how well it helps teams do real work—not by the number of features or technical terms.',
      items: [
        { title: 'Start with real work', description: 'Design around workflows that teams actually use.' },
        { title: 'Make complexity useful', description: 'Turn technology into practical, understandable tools for the working day.' },
        { title: 'Build for trust and growth', description: 'Develop products organizations can depend on and grow with.' },
      ],
    },
    geem: {
      eyebrow: 'Carrying the approach forward',
      title: 'GEEM turns operating experience into intelligence your team can use',
      description:
        'GEEM supports everyday writing, ideas and coding, alongside Experts connected to business knowledge and systems. Organizations can use GEEM cloud or tailored infrastructure we provide at their site.',
      points: [
        'Experts grounded in organizational knowledge and workspace permissions',
        'An Arabic-first experience with support for other languages',
        'Available in chat, WhatsApp, websites, and API integrations',
        'Already embedded and functioning in DALSEEN ERP, DALSEEN Platform and Qaf Noon',
      ],
    },
    cta: {
      title: 'Bring GEEM into the way your organization works',
      description: 'Discuss your knowledge, channels and systems, and choose an operating environment and capacity that fit your needs.',
      primaryCta: 'Talk with the GEEM team',
      secondaryCta: 'Explore the product',
    },
  },
  contact: {
    title: 'Contact the GEEM team',
    lead: 'Tell us about your workflow, systems and expected usage. Discuss GEEM cloud or tailored infrastructure at your site with our team.',
    salesLabel: 'Sales',
    infoLabel: 'General inquiries',
    phoneLabel: 'Phone',
    addressLabel: 'Address',
    workspaceHint: 'Existing customers can sign in to the workspace for setup and support.',
  },
  legal: {
    lastUpdatedLabel: 'Last updated',
    lastUpdated: '10 September 2026',
    operatorLabel: 'Operator',
    contactLabel: 'Data contact',
    contentsLabel: 'Document contents',
    relatedLabel: 'Related documents',
    pages: {
      privacy: {
        hero: {
          eyebrow: 'Privacy at Geem',
          title: 'A privacy policy written in plain language',
          description: 'This policy explains what we process to operate Geem, your organization’s role in managing its workspace, and the choices available to you.',
        },
        highlights: [
          { title: 'A workspace your organization manages', description: 'Your organization chooses members, roles, approved knowledge, and integrations.' },
          { title: 'Only what is needed', description: 'We do not sell personal data or private organizational knowledge.' },
          { title: 'Rights you can exercise', description: 'You can contact us about access, correction, or destruction requests where the law applies.' },
        ],
        scopeNotice: 'This policy applies to Geem websites, accounts, workspaces, and sales and support services. Your organization’s agreement or the Personal Data Protection Notice may provide additional terms.',
        sections: [
          {
            id: 'scope',
            title: 'Operator and scope',
            paragraphs: [
              'Dal Seen Information Technology Company operates Geem. This policy applies when you visit Geem websites, create an account, access a workspace, contact sales or support, or otherwise use Geem services.',
              'Dal Seen generally acts as controller for account records, website enquiries, and security logs. For private workspace content, the customer organization generally acts as controller and Dal Seen processes the data under the applicable agreement.',
            ],
          },
          {
            id: 'data',
            title: 'Data we may process',
            paragraphs: ['The data depends on how you use Geem and the features your organization enables. It may include:'],
            bullets: [
              'Identity, contact, account, membership, and permission data.',
              'Documents, content, and knowledge your organization authorizes Geem to use.',
              'Billing, support, and commercial communication records where applicable.',
              'Technical and security data needed to operate and protect the service.',
            ],
          },
          {
            id: 'purposes',
            title: 'Why we use data',
            paragraphs: [
              'We use data to create and secure accounts, provide workspaces, Experts, and channels, retrieve authorized knowledge, support customers, issue invoices where applicable, prevent misuse, and meet legal obligations.',
              'The applicable legal basis depends on the relationship and purpose and may include performing a contract, meeting a legal obligation, legitimate interests where permitted, or consent when required.',
            ],
          },
          {
            id: 'sources',
            title: 'How we collect data',
            paragraphs: ['We receive data from three main sources:'],
            bullets: [
              'Directly from you when you register, communicate with us, or use the service.',
              'From your organization when it invites you to a workspace or manages your role and permissions.',
              'From devices, services, and integrations your organization enables, including technical logs needed for operation and security.',
            ],
          },
          {
            id: 'ai-processing',
            title: 'Hosting and AI processing',
            paragraphs: [
              'In GEEM cloud, core workspace data is stored in Saudi Arabia. For client-site deployment, storage and processing arrangements follow the agreed deployment scope. Some AI features and external integrations may require the minimum necessary data to be processed by contracted service providers, as described by the applicable agreement and privacy terms.',
              'Your organization controls the knowledge sources and integrations it connects and should not add data it is not authorized to use.',
            ],
          },
          {
            id: 'cookies',
            title: 'Cookies',
            paragraphs: [
              'Geem uses essential cookies and similar local technologies for sessions, security, and locale. This website does not load marketing trackers unless we later disclose an approved provider and the purpose for using it.',
            ],
          },
          {
            id: 'disclosure',
            title: 'Disclosure and service providers',
            paragraphs: [
              'We do not sell personal data or private organizational knowledge. Minimum necessary data may be disclosed to contracted service providers, the organization administering your workspace, or competent authorities when legally required.',
            ],
          },
          {
            id: 'retention',
            title: 'Retention and protection',
            paragraphs: [
              'We retain data for as long as needed to provide the service and meet legal and contractual requirements. We use logical workspace isolation, server-enforced permissions, and controls that protect integration secrets and access keys.',
            ],
          },
          {
            id: 'rights',
            title: 'Your rights and how to contact us',
            paragraphs: [
              'You may request access, correction, destruction, or withdrawal of consent where applicable, subject to the Saudi Personal Data Protection Law, its regulations, and identity verification.',
              'Send your request to info@dalseen.sa with a clear description and the relevant workspace, if any.',
            ],
          },
        ],
        relatedLinks: [
          { label: 'Security at Geem', href: 'security' },
          { label: 'Personal Data Protection Notice', href: 'pdpl' },
          { label: 'Terms of Use', href: 'terms' },
        ],
        cta: {
          title: 'Have a question about your data?',
          description: 'Contact us for more information about privacy, data flows, or exercising your rights.',
          label: 'Contact Dal Seen',
        },
      },
      terms: {
        hero: {
          eyebrow: 'Using Geem',
          title: 'Clear terms for using the platform',
          description: 'These terms explain the responsibilities of Dal Seen, customer organizations, and users when creating a workspace or using Geem Experts and channels.',
        },
        highlights: [
          { title: 'Lawful use', description: 'Use Geem, its keys, and its integrations only for authorized and lawful purposes.' },
          { title: 'Human review', description: 'Review important outputs before relying on them in a decision or action.' },
          { title: 'Your data remains yours', description: 'Customers retain their rights in the data and content they submit.' },
        ],
        scopeNotice: 'These general terms apply unless an enterprise agreement or order form provides specific terms. Where they conflict, the specific document controls within its scope.',
        sections: [
          {
            id: 'acceptance',
            title: 'Acceptance and scope',
            paragraphs: [
              'These terms govern access to and use of Geem. Registration, a workspace invitation, or an enterprise agreement may present additional terms for the requested service.',
              'If you use Geem for an organization, you must have the authority needed to accept the applicable terms and commitments.',
            ],
          },
          {
            id: 'accounts',
            title: 'Accounts and workspaces',
            paragraphs: [
              'Workspaces are administered by the customer organization. The organization controls members, roles, authorized knowledge, and integrations within the service scope.',
              'You are responsible for accurate account information, protecting your sign-in methods, and notifying us of any known unauthorized use.',
            ],
          },
          {
            id: 'acceptable-use',
            title: 'Acceptable and prohibited use',
            paragraphs: ['Use Geem only for lawful purposes and within the permissions granted to you. In particular, you must not:'],
            bullets: [
              'Bypass security controls or attempt to access another workspace or data without authorization.',
              'Misuse API keys or share sign-in credentials insecurely.',
              'Submit unlawful content or content you are not authorized to use or process.',
              'Use the service to harm others, disrupt the platform, or test it without written approval.',
            ],
          },
          {
            id: 'ai-outputs',
            title: 'AI outputs',
            paragraphs: [
              'Geem generates probabilistic outputs that may be incomplete or incorrect. Review important outputs and apply appropriate human oversight, particularly for financial, legal, employment, or other high-impact decisions.',
              'Geem outputs do not by themselves make a legally binding decision about an individual and do not replace specialized professional advice.',
            ],
          },
          {
            id: 'content',
            title: 'Customer content and intellectual property',
            paragraphs: [
              'Geem’s platform, marks, software, and documentation remain owned by Dal Seen or its licensors. Customers retain rights in the data and content they submit.',
              'The customer gives Dal Seen only the permissions needed to process that content to provide and protect the service under the applicable agreement and Privacy Policy.',
            ],
          },
          {
            id: 'integrations',
            title: 'Integrations and third-party services',
            paragraphs: [
              'Customers may connect Geem to external services such as cloud storage, WhatsApp, or internal systems. Those services are governed by their providers’ terms, and the customer is responsible for selecting them and granting appropriate permissions.',
            ],
          },
          {
            id: 'commercial',
            title: 'Subscriptions and service limits',
            paragraphs: [
              'Fees, limits, quotas, subscription periods, and any additional commitments are defined by the applicable plan, order form, or enterprise agreement. Experimental or free features may change or end after reasonable notice.',
            ],
          },
          {
            id: 'suspension',
            title: 'Suspension and termination',
            paragraphs: [
              'Access may be suspended or limited where there is a security risk, prohibited use, overdue payment, or a need to protect the platform or its users. Termination and data-handling provisions follow the applicable agreement.',
            ],
          },
          {
            id: 'law',
            title: 'Governing law and language',
            paragraphs: [
              'These terms are governed by the laws of Saudi Arabia. The Arabic version of the public terms controls if the language versions differ, unless a signed enterprise agreement states otherwise.',
            ],
          },
        ],
        relatedLinks: [
          { label: 'Privacy Policy', href: 'privacy' },
          { label: 'Personal Data Protection Notice', href: 'pdpl' },
          { label: 'Security at Geem', href: 'security' },
        ],
        cta: {
          title: 'Does your organization need specific terms?',
          description: 'Contact us to discuss usage scope, integrations, or enterprise contracting requirements.',
          label: 'Discuss your requirements',
        },
      },
      pdpl: {
        hero: {
          eyebrow: 'Personal data protection',
          title: 'Your rights under Saudi law',
          description: 'This notice supplements the Privacy Policy and explains roles, rights, and how to submit a personal data request.',
        },
        highlights: [
          { title: 'Right to be informed', description: 'Understand the purpose, basis, and parties that may receive your data.' },
          { title: 'Access and correction', description: 'Request a readable copy and correction of inaccurate data where applicable.' },
          { title: 'Request destruction', description: 'Request destruction when the conditions under the law are met.' },
        ],
        scopeNotice: 'This notice supplements the Privacy Policy and should be read with it and the agreement governing your organization’s workspace.',
        sections: [
          { id: 'framework', title: 'Legal framework', paragraphs: ['This notice is informed by the Saudi Personal Data Protection Law, its Implementing Regulations, and the regulation governing transfers of personal data outside the Kingdom.'] },
          { id: 'controller', title: 'Controller', paragraphs: ['Dal Seen generally acts as controller for account, direct communication, and security data. For customer workspace data, the organization generally acts as controller and Dal Seen processes the data under the applicable agreement.'] },
          { id: 'rights', title: 'Rights', paragraphs: ['Subject to the law and identity verification, you may request to be informed, access data, obtain a readable copy, correct it, request destruction, and withdraw consent where consent is the basis of processing.'] },
          { id: 'requests', title: 'Exercising your rights', paragraphs: ['Email info@dalseen.sa with the subject “Personal Data Request”. We aim to respond within the period permitted by applicable laws and regulations after verifying identity and the scope of the request.'] },
          { id: 'complaints', title: 'Complaints', paragraphs: ['If you are dissatisfied with the handling of your request, you may complain to the Saudi Data and AI Authority through the National Data Governance Platform using its available procedures.'] },
          { id: 'ai', title: 'AI-assisted processing', paragraphs: ['Geem uses AI-assisted processing to retrieve authorized knowledge, generate text, and operate the service. Outputs do not by themselves make a legally binding decision about an individual.'] },
        ],
        relatedLinks: [
          { label: 'Privacy Policy', href: 'privacy' },
          { label: 'Security at Geem', href: 'security' },
          { label: 'Terms of Use', href: 'terms' },
        ],
        cta: {
          title: 'Want to exercise one of your rights?',
          description: 'Send a clear personal data request and we will help direct it to the appropriate party.',
          label: 'Contact us about your data',
        },
      },
    },
  },
};
