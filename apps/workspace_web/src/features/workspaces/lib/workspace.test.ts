import { describe, expect, it } from 'vitest';
import {
  extractHostWorkspaceSlug,
  suggestSlugFromName,
} from '@/features/workspaces/lib/hostname';
import {
  canDeleteWorkspace,
  canManageMembers,
  canManageWorkspace,
  canPromoteToOwner,
} from '@/features/workspaces/lib/roles';
import { workspaceQueryKey } from '@/services/api/query-keys';
import { errorMessageKey } from '@/services/api/errors';
import en from '@/locales/en.json';
import ar from '@/locales/ar.json';

describe('hostname slug extraction', () => {
  it('parses acme.localhost and production hosts', () => {
    expect(extractHostWorkspaceSlug('acme.localhost', 'localhost')).toBe('acme');
    expect(extractHostWorkspaceSlug('acme.geem.ai', 'geem.ai')).toBe('acme');
    expect(extractHostWorkspaceSlug('localhost', 'localhost')).toBeNull();
    expect(extractHostWorkspaceSlug('geem.ai', 'geem.ai')).toBeNull();
  });

  it('rejects reserved infrastructure hosts', () => {
    expect(extractHostWorkspaceSlug('api.geem.ai', 'geem.ai')).toBeNull();
    expect(extractHostWorkspaceSlug('admin.geem.ai', 'geem.ai')).toBeNull();
    expect(extractHostWorkspaceSlug('www.geem.ai', 'geem.ai')).toBeNull();
    expect(extractHostWorkspaceSlug('www.localhost', 'localhost')).toBeNull();
    expect(extractHostWorkspaceSlug('api.localhost', 'localhost')).toBeNull();
  });
});

describe('slug suggestion', () => {
  it('normalizes display names', () => {
    expect(suggestSlugFromName('Acme Research')).toBe('acme-research');
  });
});

describe('role helpers', () => {
  it('matches owner/admin/member UX matrix', () => {
    expect(canManageWorkspace('owner')).toBe(true);
    expect(canManageWorkspace('admin')).toBe(true);
    expect(canManageWorkspace('member')).toBe(false);
    expect(canManageMembers('member')).toBe(false);
    expect(canPromoteToOwner('admin')).toBe(false);
    expect(canPromoteToOwner('owner')).toBe(true);
    expect(canDeleteWorkspace('owner')).toBe(true);
    expect(canDeleteWorkspace('admin')).toBe(false);
  });
});

describe('query keys', () => {
  it('nests workspace identity', () => {
    expect(workspaceQueryKey('ws-1', 'members')).toEqual([
      'workspace',
      'ws-1',
      'members',
    ]);
  });
});

describe('i18n coverage', () => {
  it('keeps auth and shell keys in en and ar', () => {
    expect(en.auth.loginTitle).toBeTruthy();
    expect(ar.auth.loginTitle).toBeTruthy();
    expect(en.shell.createWorkspace).toBeTruthy();
    expect(ar.shell.createWorkspace).toBeTruthy();
    expect(en.errors.invalidCredentials).toBeTruthy();
    expect(ar.errors.sessionExpired).toBeTruthy();
    expect(errorMessageKey('invalid_credentials')).toBe('errors.invalidCredentials');
  });

  it('has matching experts keys in en and ar', () => {
    type LocaleWithExperts = typeof en & { experts: Record<string, unknown> };
    const enL = en as unknown as LocaleWithExperts;
    const arL = ar as unknown as LocaleWithExperts;
    expect(enL.experts).toBeTruthy();
    expect(arL.experts).toBeTruthy();
    // Spot check critical keys
    expect((enL.experts as Record<string, string>).create).toBeTruthy();
    expect((arL.experts as Record<string, string>).create).toBeTruthy();
    expect((enL.experts as Record<string, string>).ask).toBeTruthy();
    expect((arL.experts as Record<string, string>).ask).toBeTruthy();
  });

  it('has expert error codes in both locales', () => {
    expect(errorMessageKey('expert_not_found')).toBe('errors.expertNotFound');
    expect(errorMessageKey('upload_type_rejected')).toBe('errors.uploadTypeRejected');
    expect(errorMessageKey('upload_too_large')).toBe('errors.uploadTooLarge');
    type LocaleWithErrors = typeof en & { errors: Record<string, string> };
    const enL = en as unknown as LocaleWithErrors;
    const arL = ar as unknown as LocaleWithErrors;
    expect(enL.errors.expertNotFound).toBeTruthy();
    expect(arL.errors.expertNotFound).toBeTruthy();
  });
});
