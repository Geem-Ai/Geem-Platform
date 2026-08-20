import { apiRequest } from './client';
import type { PlatformMeResponse } from './types';

export async function fetchPlatformMe(): Promise<PlatformMeResponse> {
  return apiRequest<PlatformMeResponse>('/api/platform/me');
}

export const platformQueryKeys = {
  me: ['platform', 'me'] as const,
};
