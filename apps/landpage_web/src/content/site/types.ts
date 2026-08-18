export type NavItem = {
  id: string;
  label: string;
  href: 'product' | 'experts' | 'integrations' | 'api' | 'security' | 'contact';
};

export type SiteCopy = {
  meta: {
    homeTitle: string;
    homeDescription: string;
    aboutTitle: string;
    aboutDescription: string;
    contactTitle: string;
    contactDescription: string;
    privacyTitle: string;
    privacyDescription: string;
    termsTitle: string;
    termsDescription: string;
    pdplTitle: string;
    pdplDescription: string;
    securityTitle: string;
    securityDescription: string;
  };
  a11y: {
    skipToContent: string;
    openMenu: string;
    closeMenu: string;
    languageSwitch: string;
  };
  brand: {
    product: string;
    tagline: string;
  };
  nav: {
    items: NavItem[];
    primaryCta: string;
    login: string;
  };
  hero: {
    eyebrow: string;
    title: string;
    description: string;
    bullets: string[];
    primaryCta: string;
    secondaryCta: string;
    tertiaryCta: string;
    imageAlt: string;
  };
  valueStrip: {
    items: { title: string; description: string }[];
  };
  experts: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    formula: string[];
    cards: { title: string; description: string }[];
    diagramCaption: string;
    note: string;
  };
  knowledge: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    sources: string[];
    outcomes: string[];
  };
  integrations: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    cta: string;
    items: { id: string; title: string; description: string }[];
  };
  channels: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    nodes: { id: string; label: string }[];
  };
  api: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    points: string[];
    sampleLabel: string;
    copyLabel: string;
    copiedLabel: string;
  };
  security: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    points: { title: string; description: string }[];
    linkLabel: string;
  };
  apps: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    items: { id: string; title: string; description: string }[];
  };
  previews: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    items: { title: string; caption: string }[];
  };
  finalCta: {
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
  };
  footer: {
    product: string;
    resources: string;
    company: string;
    legal: string;
    productLinks: { label: string; href: string }[];
    resourceLinks: { label: string; href: string }[];
    companyLinks: { label: string; href: string }[];
    legalLinks: { label: string; href: string }[];
    rights: string;
    madeIn: string;
  };
  about: {
    title: string;
    lead: string;
    paragraphs: string[];
  };
  contact: {
    title: string;
    lead: string;
    salesLabel: string;
    infoLabel: string;
    phoneLabel: string;
    addressLabel: string;
    workspaceHint: string;
  };
  legal: {
    lastUpdatedLabel: string;
    lastUpdated: string;
    notice: string;
  };
};
