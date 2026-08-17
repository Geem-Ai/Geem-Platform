export function toAbsoluteUrl(pathname: string): string {
  const baseUrl = import.meta.env.BASE_URL;

  if (baseUrl && baseUrl !== '/') {
    return `${baseUrl.replace(/\/$/, '')}${pathname.startsWith('/') ? pathname : `/${pathname}`}`;
  }

  return pathname;
}

export const GEEM_AVATAR_PATH = '/brand/geem-avatar.webp';

/** Waving mascot used on Chat starter / assistant bubbles. */
export const GEEM_ANIMATED_AVATAR_PATH = '/brand/geem-animated.svg';

export function geemAvatarUrl(): string {
  return toAbsoluteUrl(GEEM_AVATAR_PATH);
}

export function geemAnimatedAvatarUrl(): string {
  return toAbsoluteUrl(GEEM_ANIMATED_AVATAR_PATH);
}
