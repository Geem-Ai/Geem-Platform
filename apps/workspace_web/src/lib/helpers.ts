export function toAbsoluteUrl(pathname: string): string {
  const baseUrl = import.meta.env.BASE_URL;

  if (baseUrl && baseUrl !== '/') {
    return `${baseUrl.replace(/\/$/, '')}${pathname.startsWith('/') ? pathname : `/${pathname}`}`;
  }

  return pathname;
}

export const GEEM_AVATAR_PATH = '/brand/geem-avatar.webp';

export function geemAvatarUrl(): string {
  return toAbsoluteUrl(GEEM_AVATAR_PATH);
}
