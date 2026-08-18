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
      'How Geem keeps your workspace, private knowledge, and team access within clear boundaries.',
  },
  a11y: {
    skipToContent: 'Skip to content',
    openMenu: 'Open menu',
    closeMenu: 'Close menu',
    languageSwitch: 'العربية',
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
      { id: 'contact', label: 'Contact', href: 'contact' },
    ],
    primaryCta: 'Start with Geem',
    login: 'Workspace Login',
  },
  hero: {
    eyebrow: 'AI for your organization',
    title: 'Turn your organization’s knowledge into AI Experts that work with your team',
    description:
      'Create Geem Experts for the work your departments do, connect them to your documents and knowledge, then use them in chat, WhatsApp, your website, and your systems — from one place.',
    bullets: [
      'Specialized Experts that follow your policies and procedures',
      'Answers based on your documents, with clear sources',
      'Team permissions so people only see what they need',
    ],
    primaryCta: 'Start with Geem',
    secondaryCta: 'Workspace Login',
    tertiaryCta: 'Explore the platform',
    imageAlt: 'Riyadh and Madinah skyline at night — Geem hero image',
  },
  valueStrip: {
    items: [
      {
        title: 'Experts for your org',
        description: 'HR, finance, operations, and more — grounded in your knowledge.',
      },
      {
        title: 'Private knowledge',
        description: 'Upload documents or connect Google Drive and OneDrive securely.',
      },
      {
        title: 'Arabic + English',
        description: 'Arabic-first experience with full English support.',
      },
      {
        title: 'Organization privacy',
        description: 'Your knowledge stays in your workspace — not a shared public library.',
      },
      {
        title: 'Where your team works',
        description: 'Chat in Geem, WhatsApp, your website, or your own systems.',
      },
    ],
  },
  experts: {
    number: '01',
    eyebrow: 'Everything starts with an Expert',
    title: 'An Expert for every task. Knowledge for every context.',
    description:
      'A Geem Expert brings together your guidance, your documents, and your organization context — so your team can rely on it wherever they work.',
    flowExpertLabel: 'Geem Expert',
    formula: ['Your guidance', 'Your documents', 'Reliable answers', 'Your context'],
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
      {
        title: 'Knowledge Expert',
        description: 'Makes your knowledge base easy to ask — with clear sources in the reply.',
      },
    ],
    diagramCaption: 'Organization knowledge → Expert → Chat / Systems / WhatsApp / Website',
    note: 'These are examples to illustrate the idea — your organization creates the Experts it needs.',
  },
  knowledge: {
    number: '02',
    eyebrow: 'Your organization’s knowledge',
    title: 'Answers grounded in the knowledge your organization trusts.',
    description:
      'Connect Experts to the sources you trust: upload PDFs and text documents, or connect Google Drive and Microsoft OneDrive. Answers can include sources you can check.',
    sources: ['PDF', 'Text documents', 'Google Drive', 'Microsoft OneDrive'],
    outcomes: [
      'Knowledge tied to each Expert',
      'Answers from your documents',
      'Clear sources in replies',
      'Private workspace',
    ],
  },
  integrations: {
    number: '03',
    eyebrow: 'Integrations',
    title: 'Connects to the tools your organization already uses.',
    description:
      'Link Geem to the knowledge and messaging tools your team already relies on — from the Geem App Store.',
    cta: 'Explore channels and apps',
    items: [
      {
        id: 'google-drive',
        title: 'Google Drive',
        description: 'Connect approved Drive files to your Experts.',
      },
      {
        id: 'microsoft-onedrive',
        title: 'Microsoft OneDrive',
        description: 'Connect OneDrive files to your workspace knowledge.',
      },
      {
        id: 'whatsapp',
        title: 'WhatsApp',
        description: 'Let a Geem Expert reply to customers or teams on WhatsApp.',
      },
      {
        id: 'chat-widget',
        title: 'Website chat',
        description: 'Add Geem chat to your organization’s website.',
      },
    ],
  },
  channels: {
    number: '04',
    eyebrow: 'Channels',
    title: 'One Expert. Many places to use it.',
    description:
      'Set up an Expert once — then your team and customers can reach it in chat, WhatsApp, your website, or your systems.',
    nodes: [
      { id: 'chat', label: 'Geem Chat' },
      { id: 'api', label: 'Your systems' },
      { id: 'whatsapp', label: 'WhatsApp' },
      { id: 'widget', label: 'Your website' },
    ],
  },
  api: {
    number: '05',
    eyebrow: 'For developers & technical teams',
    title: 'Connect Geem Experts to your systems.',
    description:
      'Your technical team can call Geem Experts from internal apps using a familiar chat-style interface — with secure keys, Expert selection, and usage visibility inside Geem.',
    points: [
      'Secure access keys for your workspace',
      'Works with common developer tooling patterns',
      'Choose the right Expert for each request',
      'Track usage inside Geem',
    ],
    sampleLabel: 'Example for your technical team',
    copyLabel: 'Copy',
    copiedLabel: 'Copied',
  },
  security: {
    number: '06',
    eyebrow: 'Trust & privacy',
    title: 'Your organization’s knowledge stays within its boundaries.',
    description:
      'Geem is built around private workspaces, approved knowledge, and controlled access — without unsupported certification claims on this site.',
    points: [
      {
        title: 'Private workspace',
        description: 'Each organization’s data and knowledge stay in its own workspace.',
      },
      {
        title: 'Only approved knowledge',
        description: 'Your Experts rely on what you allow — not a shared public library.',
      },
      {
        title: 'Protected connections',
        description: 'Connection details for Drive, OneDrive, and other apps are stored securely.',
      },
      {
        title: 'Controlled system access',
        description: 'Links to your systems use access keys belonging to your workspace.',
      },
    ],
    linkLabel: 'Read more about security',
  },
  apps: {
    number: '07',
    eyebrow: 'App Store',
    title: 'Extend Geem for what your organization needs.',
    description:
      'Add apps that connect Geem to your knowledge and customer channels. This page focuses on capabilities, not pricing.',
    items: [
      {
        id: 'google-drive',
        title: 'Google Drive',
        description: 'Knowledge from approved Drive files.',
      },
      {
        id: 'microsoft-onedrive',
        title: 'Microsoft OneDrive',
        description: 'Knowledge from OneDrive files.',
      },
      {
        id: 'whatsapp',
        title: 'WhatsApp',
        description: 'Reach people on WhatsApp with a Geem Expert.',
      },
      {
        id: 'chat-widget',
        title: 'Website chat',
        description: 'Chat on your website for customers or visitors.',
      },
    ],
  },
  previews: {
    number: '08',
    eyebrow: 'The experience',
    title: 'A clear workspace for your team.',
    description:
      'Snapshots of Geem: choosing an Expert, chatting, knowledge, apps, and team access.',
    items: [
      { title: 'Choose an Expert', caption: 'Start with the Expert that fits the task.' },
      { title: 'Conversation', caption: 'Ask and get answers from your organization’s knowledge.' },
      { title: 'Knowledge', caption: 'Upload documents or connect Drive and OneDrive.' },
      { title: 'Apps', caption: 'Add integrations from the Geem App Store.' },
      { title: 'Team access', caption: 'Decide who can see and do what in the workspace.' },
    ],
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
