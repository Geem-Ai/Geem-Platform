/**
 * Microsoft File Picker v8 (popup + postMessage / MessagePort).
 *
 * Picker access tokens stay memory-only for the session — never localStorage /
 * sessionStorage / URL params. Backend refresh credentials never reach React.
 *
 * @see https://learn.microsoft.com/en-us/onedrive/developer/controls/file-pickers/
 */

export type OneDrivePickerSession = {
  /** Short-lived SharePoint-audience token for File Picker form POST (memory-only). */
  accessToken: string;
  baseUrl: string;
  clientId?: string | null;
  tenant?: string | null;
  driveId?: string | null;
  /** Called when Picker requests a SharePoint-resource token. */
  getResourceToken: (resource: string) => Promise<string>;
};

export type OneDrivePickerSelectedFile = {
  driveId: string;
  itemId: string;
  /** Display-only — backend revalidates; do not trust for ingest. */
  name?: string;
};

export type OpenOneDrivePickerOptions = {
  session: OneDrivePickerSession;
  multiSelect?: boolean;
  onPicked: (files: OneDrivePickerSelectedFile[]) => void;
  onCancel?: () => void;
};

type PickerCommand = {
  command?: string;
  resource?: string;
  type?: string;
  items?: Array<Record<string, unknown>>;
};

function channelId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `geem-od-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function extractItems(command: PickerCommand): OneDrivePickerSelectedFile[] {
  const raw = command.items ?? [];
  const out: OneDrivePickerSelectedFile[] = [];
  for (const item of raw) {
    const id = String(item.id ?? item.ItemId ?? '').trim();
    const parent = (item.parentReference ?? item.ParentReference ?? {}) as Record<
      string,
      unknown
    >;
    const driveId = String(
      parent.driveId ?? parent.DriveId ?? item.driveId ?? '',
    ).trim();
    if (!id || !driveId) continue;
    out.push({
      driveId,
      itemId: id,
      name: typeof item.name === 'string' ? item.name : undefined,
    });
  }
  return out;
}

/**
 * Open Microsoft File Picker v8 in a popup. Resolves when the popup closes
 * or pick/cancel completes.
 */
export function openOneDrivePicker(
  options: OpenOneDrivePickerOptions,
): Promise<void> {
  const { session, multiSelect = true, onPicked, onCancel } = options;
  const baseUrl = session.baseUrl.replace(/\/$/, '');
  const win = window.open('', 'GeemOneDrivePicker', 'width=1080,height=680');
  if (!win) {
    return Promise.reject(new Error('popup_blocked'));
  }

  const id = channelId();
  const pickerOptions = {
    sdk: '8.0',
    entry: {
      oneDrive: {},
    },
    authentication: {},
    messaging: {
      origin: window.location.origin,
      channelId: id,
    },
    selection: {
      mode: multiSelect ? 'multiple' : 'single',
    },
    typesAndSources: {
      mode: 'files',
      pivots: {
        oneDrive: true,
        recent: true,
        shared: false,
        sharedLibraries: false,
        site: false,
      },
    },
  };

  const query = new URLSearchParams({
    filePicker: JSON.stringify(pickerOptions),
    locale: document.documentElement.lang || 'en-us',
  });
  const url = `${baseUrl}/_layouts/15/FilePicker.aspx?${query.toString()}`;

  const form = win.document.createElement('form');
  form.setAttribute('action', url);
  form.setAttribute('method', 'POST');
  const tokenInput = win.document.createElement('input');
  tokenInput.setAttribute('type', 'hidden');
  tokenInput.setAttribute('name', 'access_token');
  tokenInput.setAttribute('value', session.accessToken);
  form.appendChild(tokenInput);
  win.document.body.append(form);
  form.submit();

  return new Promise((resolve) => {
    let port: MessagePort | null = null;
    let settled = false;

    const finish = () => {
      if (settled) return;
      settled = true;
      window.removeEventListener('message', onMessage);
      try {
        port?.close();
      } catch {
        /* ignore */
      }
      resolve();
    };

    const onMessage = (event: MessageEvent) => {
      if (event.source !== win) return;
      const data = event.data as {
        type?: string;
        id?: string;
        data?: PickerCommand;
        channelId?: string;
      };
      if (!data || data.type !== 'initialize' || data.channelId !== id) {
        // Establish port from initialize handshake.
      }
      if (data?.type === 'initialize' && event.ports?.[0]) {
        port = event.ports[0];
        port.start();
        port.postMessage({ type: 'activate' });
        port.onmessage = (portEvent: MessageEvent) => {
          void handlePortMessage(portEvent);
        };
        return;
      }
    };

    async function handlePortMessage(portEvent: MessageEvent) {
      if (!port) return;
      const message = portEvent.data as {
        type?: string;
        id?: string;
        data?: PickerCommand;
      };
      if (!message || message.type !== 'command' || !message.data) return;

      port.postMessage({ type: 'acknowledge', id: message.id });

      const command = message.data;
      switch (command.command) {
        case 'authenticate': {
          try {
            const resource = String(command.resource || baseUrl);
            const token = await session.getResourceToken(resource);
            port.postMessage({
              type: 'result',
              id: message.id,
              data: { result: 'token', token },
            });
          } catch {
            port.postMessage({
              type: 'result',
              id: message.id,
              data: { result: 'error', error: { code: 'unableToObtainToken' } },
            });
          }
          break;
        }
        case 'pick': {
          const files = extractItems(command);
          port.postMessage({
            type: 'result',
            id: message.id,
            data: { result: 'success' },
          });
          try {
            win?.close();
          } catch {
            /* ignore */
          }
          if (files.length > 0) {
            onPicked(files);
          } else {
            onCancel?.();
          }
          finish();
          break;
        }
        case 'close': {
          port.postMessage({
            type: 'result',
            id: message.id,
            data: { result: 'success' },
          });
          try {
            win?.close();
          } catch {
            /* ignore */
          }
          onCancel?.();
          finish();
          break;
        }
        default:
          break;
      }
    }

    window.addEventListener('message', onMessage);

    const poll = window.setInterval(() => {
      if (win.closed) {
        window.clearInterval(poll);
        if (!settled) {
          onCancel?.();
          finish();
        }
      }
    }, 500);
  });
}
