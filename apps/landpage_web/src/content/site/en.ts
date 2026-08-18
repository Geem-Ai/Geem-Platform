import type { SiteCopy } from './types';

export const en: SiteCopy = {
  meta: {
    homeTitle: 'Geem | AI Experts grounded in your organization',
    homeDescription:
      'Turn your organization’s knowledge into AI Experts your team can use in chat, WhatsApp, your website, and your systems.',
    aboutTitle: 'About Geem and DALSEEN',
    aboutDescription:
      'Geem is an AI platform for organizations, built by Dal Seen Information Technology Company in Madinah.',
    contactTitle: 'Contact Geem',
    contactDescription: 'Talk with the Geem team about Experts, knowledge, and channels for your organization.',
    privacyTitle: 'Privacy Policy',
    privacyDescription: 'How Dal Seen protects your data when you use Geem.',
    termsTitle: 'Terms of Use',
    termsDescription: 'General terms for using the Geem platform.',
    pdplTitle: 'Personal Data Protection Notice',
    pdplDescription: 'Personal data protection notice for Geem users.',
    securityTitle: 'Security and your organization’s privacy',
    securityDescription:
      'Learn how Geem isolates workspaces, enforces server-side permissions, and protects integration secrets and access keys.',
  },
  a11y: {
    skipToContent: 'Skip to content',
    openMenu: 'Open menu',
    closeMenu: 'Close menu',
    primaryNavigation: 'Primary navigation',
    mobileNavigation: 'Mobile navigation',
    languageSwitch: 'العربية',
    pauseTypewriter: 'Pause rotating phrases',
    resumeTypewriter: 'Resume rotating phrases',
  },
  brand: {
    product: 'Geem',
    tagline: 'AI that works with your organization’s knowledge',
  },
  nav: {
    items: [
      { id: 'product', label: 'Product', href: 'product' },
      { id: 'experts', label: 'Experts', href: 'experts' },
      { id: 'integrations', label: 'Integrations', href: 'integrations' },
      { id: 'api', label: 'Developers', href: 'api' },
      { id: 'security', label: 'Security', href: 'security' },
    ],
    primaryCta: 'Start with Geem',
    login: 'Workspace Login',
  },
  hero: {
    eyebrow: 'An AI platform purpose-built for the Saudi market',
    specialtyPrompt: 'Need an Expert in',
    specialties: [
      'Human Resources',
      'Finance',
      'Marketing',
      'Sales',
      'Operations',
      'Customer Support',
    ],
    description:
      'Create a Geem Expert for each function, connect the documents it should use, and make it available in your workspace, on your website, through WhatsApp, or in internal systems.',
    primaryCta: 'Start with Geem',
    tertiaryCta: 'See how it works',
    imageAlt: 'Riyadh and Madinah skyline at night — Geem hero image',
  },
  valueStrip: {
    items: [
      {
        title: 'Built for Saudi organizations first',
        description: 'An Arabic-first platform, built in Madinah around the needs of organizations in Saudi Arabia.',
      },
      {
        title: 'Core data stored in Saudi Arabia',
        description: 'Core workspace data is stored on infrastructure located in Saudi Arabia.',
      },
      {
        title: 'First-class Arabic support',
        description: 'Geem is designed for a complete Arabic experience, with seamless use of other supported languages.',
      },
    ],
  },
  experts: {
    number: '01',
    eyebrow: 'Everything starts with an Expert',
    title: 'Build an Expert for every job your team needs.',
    description:
      'Define its role, connect the knowledge it may use, and give your team answers with sources they can review.',
    flowExpertLabel: 'Geem Expert',
    formula: ['Its role', 'Approved knowledge', 'Answers with sources', 'Workspace context'],
    cards: [
      {
        title: 'HR Expert',
        description: 'Answers leave and hiring questions from your approved HR documents.',
      },
      {
        title: 'Finance Expert',
        description: 'Helps your finance team with answers based on internal knowledge.',
      },
      {
        title: 'Operations Expert',
        description: 'Guides staff using your playbooks and day-to-day procedures.',
      },
    ],
    diagramCaption: 'Organization knowledge → Expert → Chat / Systems / WhatsApp / Website',
    note: 'Examples only — your organization defines the Experts it needs.',
  },
  knowledge: {
    eyebrow: 'Approved knowledge',
    sources: ['PDF', 'Text documents', 'Google Drive', 'Microsoft OneDrive'],
  },
  integrations: {
    number: '02',
    eyebrow: 'Apps & integrations',
    title: 'Connect the sources and channels your team already uses.',
    description:
      'Bring approved files from Drive or OneDrive into Geem, then make an Expert available through WhatsApp or your website.',
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
      eyebrow: 'Beyond chat',
      title: 'Geem is more than a chatbot.',
      description:
        'Through the API, your technical team can bring Geem Expert answers grounded in your organization’s knowledge into ERP and internal tools, supporting employees with relevant information as decisions are made.',
      tags: ['ERP systems', 'Internal tools', 'Human decision support'],
    },
  },
  channels: {
    number: '03',
    eyebrow: 'Channels',
    title: 'One Expert, available where work happens.',
    description:
      'Configure an Expert once, then make it available to your team and customers in Geem Chat, WhatsApp, your website, or internal systems.',
    nodes: [
      {
        id: 'chat',
        label: 'Geem Chat',
        context: 'For your team',
        description: 'Ask the Expert in your workspace and trace answers to their sources.',
      },
      {
        id: 'api',
        label: 'API & systems',
        context: 'For your systems',
        description: 'Bring Expert answers into your internal tools.',
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
    eyebrow: 'For developers & technical teams',
    title: 'Bring the same Expert into your internal tools.',
    description:
      'Use a familiar Chat Completions request format, choose the Expert by header, and manage keys and usage from the workspace.',
    points: [
      'Familiar Chat Completions format',
      'Scoped, revocable workspace keys',
      'Expert selection and usage visibility',
    ],
    sampleLabel: 'Example for your technical team',
    copyLabel: 'Copy',
    copiedLabel: 'Copied',
  },
  security: {
    number: '05',
    eyebrow: 'Trust & privacy',
    title: 'Clear boundaries for your organization’s knowledge.',
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
        eyebrow: 'Security & privacy at Geem',
        title: 'Clear boundaries for your organization’s knowledge.',
        description:
          'Geem is built with logical workspace isolation, server-enforced permissions, and protection for integration secrets and access keys.',
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
          { id: 'residency', label: 'Core data in Saudi Arabia' },
        ],
      },
      facts: [
        { value: 'In Saudi Arabia', label: 'Core workspace data storage' },
        { value: 'Logically isolated', label: 'Each organization’s knowledge' },
        { value: 'Server enforced', label: 'Roles and permissions' },
      ],
      controls: {
        eyebrow: 'Core safeguards',
        title: 'Protection starts before an answer is returned.',
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
        title: 'Geem provides the controls. Your organization decides who can reach what.',
        description:
          'Access and knowledge remain deliberate choices for your organization, while Geem enforces the technical boundaries inside the platform.',
        geemTitle: 'What Geem protects',
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
        title: 'Clear controls, accurately described.',
        description:
          'Core workspace data is stored in Saudi Arabia. Some AI features and external integrations may require the minimum necessary data to be processed by service providers, as described in the agreement and Privacy Policy.',
        note:
          'Before contracting, your team can request a data-flow overview and the agreed processing scope. We do not display certifications or compliance levels that have not been verified.',
      },
      cta: {
        title: 'Does your team have specific security requirements?',
        description: 'Talk with us to review the controls, data flow, and your organization’s needs before you start.',
        primaryCta: 'Contact the Geem team',
        privacyCta: 'Privacy Policy',
        pdplCta: 'Data Protection Notice',
      },
    },
  },
  finalCta: {
    title: 'Ready to build Geem Experts for your organization?',
    description:
      'Create a workspace, set up your Experts, and connect your documents and channels in one place.',
    primaryCta: 'Start with Geem',
    secondaryCta: 'Contact the team',
  },
  footer: {
    product: 'Product',
    resources: 'Resources',
    company: 'Company',
    legal: 'Legal',
    productLinks: [
      { label: 'Platform', href: 'product' },
      { label: 'Experts', href: 'experts' },
      { label: 'Integrations', href: 'integrations' },
      { label: 'Developers', href: 'api' },
      { label: 'Workspace Login', href: 'login' },
    ],
    resourceLinks: [
      { label: 'Security', href: 'security' },
    ],
    companyLinks: [
      { label: 'About DALSEEN', href: 'about' },
      { label: 'Contact', href: 'contact' },
    ],
    legalLinks: [
      { label: 'Privacy', href: 'privacy' },
      { label: 'Terms', href: 'terms' },
      { label: 'Data protection', href: 'pdpl' },
    ],
    rights: 'All rights reserved by Dal Seen Information Technology Company.',
    madeIn: 'Made in Madinah',
  },
  about: {
    title: 'About Geem and DALSEEN',
    lead: 'Geem is an AI platform for organizations, built by Dal Seen Information Technology Company in Madinah.',
    paragraphs: [
      'Geem helps organizations turn private knowledge into AI Experts that teams can use in chat, WhatsApp, the website, and internal systems — with clear permissions and a private workspace.',
      'DALSEEN is a Saudi product company. We keep a clear Saudi identity, including “Made in Madinah,” without inventing certifications or unsupported numbers.',
      'This site introduces Geem. Commercial details are handled through contact or inside the workspace, based on your subscription and the apps you enable.',
    ],
  },
  contact: {
    title: 'Contact the Geem team',
    lead: 'Tell us about your organization and what you need from Experts, knowledge, and channels. Reach us through the contacts below.',
    salesLabel: 'Sales',
    infoLabel: 'General inquiries',
    phoneLabel: 'Phone',
    addressLabel: 'Address',
    workspaceHint: 'Existing customers can sign in to the workspace for setup and support.',
  },
  legal: {
    lastUpdatedLabel: 'Last updated',
    lastUpdated: '18 August 2026',
    notice:
      'Adapted from the previously published geem.ai notice to match the current Geem platform. Final legal review is recommended before treating this as the production document of record.',
  },
};
