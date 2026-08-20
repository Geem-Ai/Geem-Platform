export type User = {
  id: string;
  email: string;
  status: string;
  platform_role: string;
  created_at: string;
  email_verified_at?: string | null;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
};

export type PlatformMeResponse = {
  user: User;
  platform_role: string;
  authorized: boolean;
};

export const PLATFORM_ROLE_ADMIN = 'admin';

export function isPlatformAdmin(user: Pick<User, 'platform_role'> | null | undefined): boolean {
  return user?.platform_role === PLATFORM_ROLE_ADMIN;
}
