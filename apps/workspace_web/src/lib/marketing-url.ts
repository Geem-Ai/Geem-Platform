const DEFAULT_MARKETING_URL = 'https://geem.ai';

/** Public marketing site origin (landpage), no trailing slash. */
export function marketingSiteUrl(): string {
  return (
    import.meta.env.VITE_MARKETING_URL?.trim().replace(/\/+$/, '') ||
    DEFAULT_MARKETING_URL
  );
}
