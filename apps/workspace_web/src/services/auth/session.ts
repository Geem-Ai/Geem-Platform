/**
 * In-memory access-token store only.
 * Refresh credentials live in HttpOnly cookies — never localStorage/sessionStorage.
 */

export type AuthSession = {
  accessToken: string | null;
  userId: string | null;
};

let session: AuthSession = {
  accessToken: null,
  userId: null,
};

export function getAuthSession(): AuthSession {
  return session;
}

export function setAuthSession(next: Partial<AuthSession>): void {
  session = { ...session, ...next };
}

export function clearAuthSession(): void {
  session = { accessToken: null, userId: null };
}
