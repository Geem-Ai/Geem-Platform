/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_SITE_URL?: string;
  readonly PUBLIC_WORKSPACE_URL?: string;
  readonly PUBLIC_SIGNUP_URL?: string;
  readonly PUBLIC_CONTACT_URL?: string;
  readonly PUBLIC_DOCS_URL?: string;
  readonly PUBLIC_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
