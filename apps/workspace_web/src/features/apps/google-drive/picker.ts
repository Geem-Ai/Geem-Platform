/**
 * Google Picker integration (Phase 9D).
 *
 * Access tokens must stay memory-only — never localStorage/sessionStorage/URL/logs.
 */

const GOOGLE_API_SCRIPT = 'https://apis.google.com/js/api.js';
const GOOGLE_GSI_SCRIPT = 'https://accounts.google.com/gsi/client';

export type GooglePickerSelectedFile = {
  id: string;
  name?: string;
  mimeType?: string;
  resourceKey?: string;
};

export type GooglePickerSession = {
  accessToken: string;
  /** Google Cloud project number (App ID). Prefer Vite env when set. */
  appId?: string | null;
  /** Picker developer key. Prefer Vite env when set. */
  developerKey?: string | null;
};

export type OpenGooglePickerOptions = {
  session: GooglePickerSession;
  multiSelect?: boolean;
  /** Called with selected Drive file IDs (and optional resource keys). */
  onPicked: (files: GooglePickerSelectedFile[]) => void;
  onCancel?: () => void;
};

type GapiClient = {
  load: (api: string, cb: () => void) => void;
};

type GooglePickerDoc = {
  id: string;
  name?: string;
  mimeType?: string;
  resourceKey?: string;
};

type GooglePickerResponse = {
  action: string;
  docs?: GooglePickerDoc[];
};

declare global {
  interface Window {
    gapi?: GapiClient;
    google?: {
      picker: {
        Action: { PICKED: string; CANCEL: string };
        DocsViewMode: { LIST: string };
        Feature: { MULTISELECT_ENABLED: string; SUPPORT_DRIVES: string };
        ViewId: { DOCS: string };
        DocsView: new (viewId?: string) => {
          setIncludeFolders: (v: boolean) => GooglePickerDocsView;
          setSelectFolderEnabled: (v: boolean) => GooglePickerDocsView;
          setMimeTypes: (mimes: string) => GooglePickerDocsView;
          setMode: (mode: string) => GooglePickerDocsView;
        };
        PickerBuilder: new () => GooglePickerBuilder;
      };
    };
  }
}

type GooglePickerDocsView = {
  setIncludeFolders: (v: boolean) => GooglePickerDocsView;
  setSelectFolderEnabled: (v: boolean) => GooglePickerDocsView;
  setMimeTypes: (mimes: string) => GooglePickerDocsView;
  setMode: (mode: string) => GooglePickerDocsView;
};

type GooglePickerBuilder = {
  addView: (view: GooglePickerDocsView) => GooglePickerBuilder;
  enableFeature: (feature: string) => GooglePickerBuilder;
  setOAuthToken: (token: string) => GooglePickerBuilder;
  setDeveloperKey: (key: string) => GooglePickerBuilder;
  setAppId: (id: string) => GooglePickerBuilder;
  setOrigin: (origin: string) => GooglePickerBuilder;
  setCallback: (cb: (data: GooglePickerResponse) => void) => GooglePickerBuilder;
  build: () => { setVisible: (v: boolean) => void };
};

const SUPPORTED_MIME_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'application/vnd.google-apps.document',
].join(',');

let apiScriptPromise: Promise<void> | null = null;

/** Open Picker instances — used so Radix Sheet/Dialog ignore outside dismiss. */
let googlePickerOpenCount = 0;
const googlePickerOpenListeners = new Set<() => void>();

function notifyGooglePickerOpenListeners(): void {
  for (const listener of googlePickerOpenListeners) {
    listener();
  }
}

function setGooglePickerOpen(open: boolean): void {
  const prev = googlePickerOpenCount;
  googlePickerOpenCount = Math.max(0, googlePickerOpenCount + (open ? 1 : -1));
  if ((prev === 0) !== (googlePickerOpenCount === 0)) {
    notifyGooglePickerOpenListeners();
  }
}

/** True while at least one Google Picker overlay is visible. */
export function isGooglePickerOpen(): boolean {
  return googlePickerOpenCount > 0;
}

/** Subscribe to Picker open/close transitions (for Sheet dismiss guards). */
export function subscribeGooglePickerOpen(listener: () => void): () => void {
  googlePickerOpenListeners.add(listener);
  return () => {
    googlePickerOpenListeners.delete(listener);
  };
}

/**
 * Mark Picker as open and wait a paint so hosts (Radix Sheet) can leave modal
 * mode before the overlay mounts — otherwise pointer-events stay blocked.
 */
async function prepareGooglePickerHost(): Promise<void> {
  setGooglePickerOpen(true);
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
}

/**
 * True when a dismiss event target belongs to Google Picker UI (div overlay or iframe).
 * Used as a belt-and-suspenders check alongside {@link isGooglePickerOpen}.
 */
export function isGooglePickerEventTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  if (target.closest('.picker, .picker-dialog, .picker-dialog-bg')) {
    return true;
  }
  if (target instanceof HTMLIFrameElement) {
    const src = target.getAttribute('src') ?? '';
    return src.includes('google.com') || src.includes('googleusercontent.com');
  }
  return false;
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === '1') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), {
        once: true,
      });
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => {
      script.dataset.loaded = '1';
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

async function ensureGoogleApis(): Promise<void> {
  if (!apiScriptPromise) {
    apiScriptPromise = (async () => {
      await Promise.all([loadScript(GOOGLE_API_SCRIPT), loadScript(GOOGLE_GSI_SCRIPT)]);
      await new Promise<void>((resolve, reject) => {
        if (!window.gapi) {
          reject(new Error('Google API failed to load'));
          return;
        }
        window.gapi.load('picker', () => resolve());
      });
    })().catch((err) => {
      apiScriptPromise = null;
      throw err;
    });
  }
  await apiScriptPromise;
}

function resolvePickerConfig(session: GooglePickerSession): {
  appId: string;
  developerKey: string;
} {
  const appId =
    (import.meta.env.VITE_GOOGLE_DRIVE_APP_ID as string | undefined)?.trim() ||
    session.appId?.trim() ||
    '';
  const developerKey =
    (import.meta.env.VITE_GOOGLE_DRIVE_PICKER_API_KEY as string | undefined)?.trim() ||
    session.developerKey?.trim() ||
    '';
  return { appId, developerKey };
}

/**
 * Open the official Google Picker. The access token is held only in the
 * closure for this call and is not written to browser storage.
 */
export async function openGooglePicker(options: OpenGooglePickerOptions): Promise<void> {
  const { session, multiSelect = true, onPicked, onCancel } = options;
  const token = session.accessToken;
  if (!token) {
    throw new Error('Missing Google Picker access token');
  }

  await ensureGoogleApis();
  const pickerNs = window.google?.picker;
  if (!pickerNs) {
    throw new Error('Google Picker unavailable');
  }

  const { appId, developerKey } = resolvePickerConfig(session);
  const view = new pickerNs.DocsView(pickerNs.ViewId.DOCS);
  view.setIncludeFolders(false);
  view.setSelectFolderEnabled(false);
  view.setMimeTypes(SUPPORTED_MIME_TYPES);
  view.setMode(pickerNs.DocsViewMode.LIST);

  let settled = false;
  const settlePicker = () => {
    if (settled) return;
    settled = true;
    setGooglePickerOpen(false);
  };

  const builder = new pickerNs.PickerBuilder()
    .addView(view)
    .enableFeature(pickerNs.Feature.SUPPORT_DRIVES)
    .setOAuthToken(token)
    .setCallback((data: GooglePickerResponse) => {
      if (data.action === pickerNs.Action.CANCEL) {
        settlePicker();
        onCancel?.();
        return;
      }
      if (data.action === pickerNs.Action.PICKED) {
        settlePicker();
        const files: GooglePickerSelectedFile[] = (data.docs ?? []).map((doc) => ({
          id: doc.id,
          name: doc.name,
          mimeType: doc.mimeType,
          resourceKey: doc.resourceKey,
        }));
        onPicked(files);
      }
    });

  if (multiSelect) {
    builder.enableFeature(pickerNs.Feature.MULTISELECT_ENABLED);
  }
  if (developerKey) {
    builder.setDeveloperKey(developerKey);
  }
  if (appId) {
    builder.setAppId(appId);
  }
  // Avoid Google defaulting parent to favicon.ico; keep postMessage origin correct.
  builder.setOrigin(window.location.origin);

  try {
    // Let Radix Sheet switch modal={false} before Picker claims the overlay.
    await prepareGooglePickerHost();
    builder.build().setVisible(true);
  } catch (err) {
    settlePicker();
    throw err;
  }
}

/** Test helper — reset cached script loader / open tracking between tests. */
export function __resetGooglePickerLoaderForTests(): void {
  apiScriptPromise = null;
  googlePickerOpenCount = 0;
  googlePickerOpenListeners.clear();
}
