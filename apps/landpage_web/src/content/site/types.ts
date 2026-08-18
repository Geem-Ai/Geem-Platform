export type NavItem = {
  id: string;
  label: string;
  href: 'product' | 'experts' | 'integrations' | 'api' | 'security' | 'contact';
};

export type SecurityPageCopy = {
  hero: {
    eyebrow: string;
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
  };
  boundary: {
    label: string;
    title: string;
    caption: string;
    items: {
      id: 'knowledge' | 'permissions' | 'credentials' | 'residency';
      label: string;
    }[];
  };
  facts: { value: string; label: string }[];
  controls: {
    eyebrow: string;
    title: string;
    description: string;
    items: {
      id: 'workspace' | 'roles' | 'integrations' | 'access';
      title: string;
      description: string;
    }[];
  };
  requestFlow: {
    eyebrow: string;
    title: string;
    description: string;
    steps: string[];
  };
  governance: {
    eyebrow: string;
    title: string;
    description: string;
    geemTitle: string;
    geemItems: string[];
    organizationTitle: string;
    organizationItems: string[];
  };
  transparency: {
    eyebrow: string;
    title: string;
    description: string;
    note: string;
  };
  cta: {
    title: string;
    description: string;
    primaryCta: string;
    privacyCta: string;
    pdplCta: string;
  };
};

export type AboutPageCopy = {
  hero: {
    eyebrow: string;
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
    companyLabel: string;
    productLabel: string;
  };
  facts: { value: string; label: string }[];
  story: {
    eyebrow: string;
    title: string;
    description: string;
    milestones: { place: string; title: string; description: string }[];
  };
  principles: {
    eyebrow: string;
    title: string;
    description: string;
    items: { title: string; description: string }[];
  };
  geem: {
    eyebrow: string;
    title: string;
    description: string;
    points: string[];
  };
  cta: {
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
  };
};

export type LegalPageKey = 'privacy' | 'terms' | 'pdpl';

export type LegalPageCopy = {
  hero: {
    eyebrow: string;
    title: string;
    description: string;
  };
  highlights: { title: string; description: string }[];
  scopeNotice: string;
  sections: {
    id: string;
    title: string;
    paragraphs: string[];
    bullets?: string[];
  }[];
  relatedLinks: { label: string; href: 'security' | LegalPageKey }[];
  cta: {
    title: string;
    description: string;
    label: string;
  };
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
    primaryNavigation: string;
    mobileNavigation: string;
    languageSwitch: string;
    pauseTypewriter: string;
    resumeTypewriter: string;
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
    specialtyPrompt: string;
    specialties: string[];
    description: string;
    primaryCta: string;
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
    flowExpertLabel: string;
    formula: string[];
    cards: { title: string; description: string }[];
    diagramCaption: string;
    note: string;
  };
  knowledge: {
    eyebrow: string;
    sources: string[];
  };
  integrations: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    items: { id: string; title: string; description: string }[];
    systemCard: {
      eyebrow: string;
      title: string;
      description: string;
      tags: string[];
    };
  };
  channels: {
    number: string;
    eyebrow: string;
    title: string;
    description: string;
    nodes: {
      id: 'chat' | 'api' | 'whatsapp' | 'widget';
      label: string;
      context: string;
      description: string;
    }[];
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
    page: SecurityPageCopy;
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
  about: AboutPageCopy;
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
    operatorLabel: string;
    contactLabel: string;
    contentsLabel: string;
    relatedLabel: string;
    pages: Record<LegalPageKey, LegalPageCopy>;
  };
};
