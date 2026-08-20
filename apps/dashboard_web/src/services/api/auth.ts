import { apiRequest } from './client';
import type { AuthTokenResponse } from './types';

export async function loginAccount(email: string, password: string): Promise<AuthTokenResponse> {
  return apiRequest<AuthTokenResponse>('/api/auth/login', {
    method: 'POST',
    json: { email, password },
    skipAuth: true,
  });
}

export async function refreshSession(): Promise<AuthTokenResponse> {
  return apiRequest<AuthTokenResponse>('/api/auth/refresh', {
    method: 'POST',
    json: {},
    skipAuth: true,
  });
}

export async function logoutSession(): Promise<void> {
  await apiRequest<void>('/api/auth/logout', {
    method: 'POST',
    json: {},
  });
}

export async function logoutAllSessions(): Promise<void> {
  await apiRequest<void>('/api/auth/logout-all', {
    method: 'POST',
  });
}
