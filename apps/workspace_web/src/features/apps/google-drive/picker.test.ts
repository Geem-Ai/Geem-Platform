import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  __resetGooglePickerLoaderForTests,
  isGooglePickerOpen,
  openGooglePicker,
  type GooglePickerSelectedFile,
} from './picker';

describe('Google Drive picker module', () => {
  beforeEach(() => {
    __resetGooglePickerLoaderForTests();
    vi.stubGlobal('gapi', {
      load: (_api: string, cb: () => void) => cb(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.head.querySelectorAll('script').forEach((s) => s.remove());
  });

  it('invokes callback with selected file ids and does not touch storage', async () => {
    const picked: GooglePickerSelectedFile[] = [];
    let storedToken: string | null = 'should-not-persist';

    const docsView = {
      setIncludeFolders: vi.fn().mockReturnThis(),
      setSelectFolderEnabled: vi.fn().mockReturnThis(),
      setMimeTypes: vi.fn().mockReturnThis(),
      setMode: vi.fn().mockReturnThis(),
    };

    let callback: ((data: { action: string; docs?: Array<{ id: string }> }) => void) | null =
      null;

    const builder = {
      addView: vi.fn().mockReturnThis(),
      enableFeature: vi.fn().mockReturnThis(),
      setOAuthToken: vi.fn().mockReturnThis(),
      setDeveloperKey: vi.fn().mockReturnThis(),
      setAppId: vi.fn().mockReturnThis(),
      setOrigin: vi.fn().mockReturnThis(),
      setCallback: vi.fn((cb) => {
        callback = cb;
        return builder;
      }),
      build: vi.fn(() => ({
        setVisible: vi.fn(() => {
          expect(isGooglePickerOpen()).toBe(true);
          callback?.({
            action: 'picked',
            docs: [{ id: 'file-1' }, { id: 'file-2' }],
          });
        }),
      })),
    };

    vi.stubGlobal('google', {
      picker: {
        Action: { PICKED: 'picked', CANCEL: 'cancel' },
        DocsViewMode: { LIST: 'list' },
        Feature: { MULTISELECT_ENABLED: 'multi', SUPPORT_DRIVES: 'drives' },
        ViewId: { DOCS: 'docs' },
        DocsView: vi.fn(function DocsView() {
          return docsView;
        }),
        PickerBuilder: vi.fn(function PickerBuilder() {
          return builder;
        }),
      },
    });

    // Pretend scripts already loaded
    const api = document.createElement('script');
    api.src = 'https://apis.google.com/js/api.js';
    api.dataset.loaded = '1';
    document.head.appendChild(api);
    const gsi = document.createElement('script');
    gsi.src = 'https://accounts.google.com/gsi/client';
    gsi.dataset.loaded = '1';
    document.head.appendChild(gsi);

    await openGooglePicker({
      session: { accessToken: 'memory-only-token', appId: '1', developerKey: 'key' },
      multiSelect: true,
      onPicked: (files) => {
        picked.push(...files);
        storedToken = null;
      },
    });

    expect(picked.map((f) => f.id)).toEqual(['file-1', 'file-2']);
    expect(isGooglePickerOpen()).toBe(false);
    expect(builder.setOAuthToken).toHaveBeenCalledWith('memory-only-token');
    expect(builder.setOrigin).toHaveBeenCalledWith(window.location.origin);
    expect(builder.enableFeature).toHaveBeenCalledWith('multi');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(storedToken).toBeNull();
  });
});
