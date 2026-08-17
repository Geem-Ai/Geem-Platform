import { geemAnimatedAvatarUrl, geemAvatarUrl } from '@/lib/helpers';
import { cn } from '@/lib/utils';

interface GeemAnimatedMascotProps {
  alt: string;
  className?: string;
  'data-testid'?: string;
}

/**
 * Chat mascot with CSS wave animation.
 * Embedded via object (not img) so browsers apply the SVG stylesheet animations.
 */
export function GeemAnimatedMascot({
  alt,
  className,
  'data-testid': testId,
}: GeemAnimatedMascotProps) {
  return (
    <object
      data={geemAnimatedAvatarUrl()}
      type="image/svg+xml"
      aria-label={alt}
      role="img"
      tabIndex={-1}
      data-testid={testId}
      data-geem-mascot="animated"
      className={cn('pointer-events-none block select-none', className)}
    >
      {/* Fallback when object embedding is unavailable */}
      <img src={geemAvatarUrl()} alt={alt} className={className} />
    </object>
  );
}
