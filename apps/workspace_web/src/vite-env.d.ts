/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_ROOT_DOMAIN?: string;
  readonly VITE_APP_ENV?: string;
  readonly VITE_CLIENT_AGENT_DOCS_URL?: string;
  readonly BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
