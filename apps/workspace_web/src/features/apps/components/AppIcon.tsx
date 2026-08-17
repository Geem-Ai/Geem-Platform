import { AppWindow } from 'lucide-react';
import { cn } from '@/lib/utils';

type AppIconProps = {
  slug: string;
  name: string;
  iconUrl?: string | null;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
};

const SIZE = {
  sm: 'size-10',
  md: 'size-12',
  lg: 'size-14',
} as const;

/** Local SVG Repo marks under public/brand/apps (?v= busts stale browser cache). */
const BRAND_ICON_BY_SLUG: Record<string, string> = {
  'google-drive': '/brand/apps/google-drive.svg?v=2',
  'microsoft-onedrive': '/brand/apps/microsoft-onedrive.svg?v=2',
  whatsapp: '/brand/apps/whatsapp.svg?v=2',
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
        <img src={src} alt="" className="size-full object-contain" />
      ) : (
        <AppWindow className="size-5 text-muted-foreground" aria-label={name} />
      )}
    </div>
  );
}
