import { describe, expect, it } from 'vitest';
import {
  clearWorkspacePreference,
  loadWorkspacePreference,
  saveWorkspacePreference,
} from '@/services/auth/workspace-context';
import { clearAuthSession, getAuthSession, setAuthSession } from '@/services/auth/session';

describe('browser storage security', () => {
  it('keeps access tokens out of localStorage', () => {
    clearAuthSession();
    setAuthSession({ accessToken: 'secret-access', userId: 'u1' });
    expect(getAuthSession().accessToken).toBe('secret-access');
    expect(localStorage.getItem('accessToken')).toBeNull();
    expect(localStorage.getItem('refreshToken')).toBeNull();
    expect(Object.keys(localStorage).every((k) => !k.toLowerCase().includes('token'))).toBe(
      true,
    );
    clearAuthSession();
  });

  it('stores only workspace preference ids', () => {
    saveWorkspacePreference('user-1', 'ws-abc');
    expect(loadWorkspacePreference('user-1')).toBe('ws-abc');
    expect(loadWorkspacePreference('user-1')).not.toContain('token');
    clearWorkspacePreference('user-1');
  });
});
