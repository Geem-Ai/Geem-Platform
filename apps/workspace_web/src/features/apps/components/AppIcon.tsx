import { AppWindow } from 'lucide-react';
import { cn } from '@/lib/utils';

type AppIconProps = {
  slug: string;
  name: string;
  iconUrl?: string | null;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
};

/** Explicit w/h (not only `size-*`) so SVG intrinsic widths cannot expand the box. */
const SIZE = {
  sm: 'size-10 w-10 h-10',
  md: 'size-12 w-12 h-12',
  lg: 'size-14 w-14 h-14',
} as const;

/** Local SVG Repo marks under public/brand/apps (?v= busts stale browser cache). */
const BRAND_ICON_BY_SLUG: Record<string, string> = {
  'google-drive': '/brand/apps/google-drive.svg?v=3',
  'microsoft-onedrive': '/brand/apps/microsoft-onedrive.svg?v=3',
  whatsapp: '/brand/apps/whatsapp.svg?v=3',
};

function resolveIconSrc(slug: string, iconUrl?: string | null): string | null {
  return BRAND_ICON_BY_SLUG[slug] ?? iconUrl ?? null;
}

export function AppIcon({ slug, name, iconUrl, className, size = 'md' }: AppIconProps) {
  const src = resolveIconSrc(slug, iconUrl);
  const box = SIZE[size];

  return (
    <div
      className={cn(
        box,
        'rounded-xl border border-border bg-background shadow-xs',
        'flex items-center justify-center shrink-0 overflow-hidden p-2',
        className,
      )}
      aria-hidden
    >
      {src ? (
        <img
          src={src}
          alt=""
          width={56}
          height={56}
          className="max-h-full max-w-full w-full h-full object-contain"
        />
      ) : (
        <AppWindow className="size-5 text-muted-foreground" aria-label={name} />
      )}
    </div>
  );
}
