const ACCEPT_PATH = '/invitations/accept';

export function isInvitationAcceptPath(raw: string | null | undefined): boolean {
  if (!raw) return false;
  const path = raw.split('?')[0] ?? raw;
  return path === ACCEPT_PATH;
}

export function invitationAcceptPath(token: string): string {
  const params = new URLSearchParams({ token });
  return `${ACCEPT_PATH}?${params.toString()}`;
}

export function readInvitationToken(search: string): string | null {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const token = params.get('token')?.trim() ?? '';
  if (!token || token.length > 256) return null;
  return token;
}
