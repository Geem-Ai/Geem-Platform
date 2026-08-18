import { apiRequest } from './client';
import type { AuthTokenResponse, MeResponse } from './types';

export async function registerAccount(email: string, password: string): Promise<AuthTokenResponse> {
  return apiRequest<AuthTokenResponse>('/api/auth/register', {
    method: 'POST',
    json: { email, password },
    skipAuth: true,
    skipWorkspace: true,
  });
}

export async function loginAccount(email: string, password: string): Promise<AuthTokenResponse> {
  return apiRequest<AuthTokenResponse>('/api/auth/login', {
    method: 'POST',
    json: { email, password },
    skipAuth: true,
    skipWorkspace: true,
  });
}

/** Cookie-based refresh — do not send refresh_token in JSON for browser path. */
export async function refreshSession(): Promise<AuthTokenResponse> {
  return apiRequest<AuthTokenResponse>('/api/auth/refresh', {
    method: 'POST',
    json: {},
    skipAuth: true,
    skipWorkspace: true,
  });
}

export async function logoutSession(): Promise<void> {
  // Prefer cookie; also send Bearer so sid can be revoked if cookie is missing.
  await apiRequest<void>('/api/auth/logout', {
    method: 'POST',
    json: {},
    skipWorkspace: true,
  });
}

export async function logoutAllSessions(): Promise<void> {
  await apiRequest<void>('/api/auth/logout-all', {
    method: 'POST',
    skipWorkspace: true,
  });
}

export async function fetchMe(): Promise<MeResponse> {
  return apiRequest<MeResponse>('/api/auth/me', {
    skipWorkspace: false,
  });
}

export async function forgotPassword(email: string): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>('/api/auth/forgot-password', {
    method: 'POST',
    json: { email },
    skipAuth: true,
    skipWorkspace: true,
  });
}

export async function resetPassword(
  token: string,
  password: string,
): Promise<AuthTokenResponse> {
  return apiRequest<AuthTokenResponse>('/api/auth/reset-password', {
    method: 'POST',
    json: { token, password },
    skipAuth: true,
    skipWorkspace: true,
  });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>('/api/auth/change-password', {
    method: 'POST',
    json: { current_password: currentPassword, new_password: newPassword },
    skipWorkspace: true,
  });
}
