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
 * Always wrap sizing on the outer box — object contents ignore some CSS max-width rules.
 */
export function GeemAnimatedMascot({
  alt,
  className,
  'data-testid': testId,
}: GeemAnimatedMascotProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center overflow-hidden',
        className,
      )}
      data-testid={testId}
      data-geem-mascot="animated"
    >
      <object
        data={geemAnimatedAvatarUrl()}
        type="image/svg+xml"
        aria-label={alt}
        role="img"
        tabIndex={-1}
        className="pointer-events-none block h-full w-full max-h-full max-w-full select-none"
      >
        {/* Fallback when object embedding is unavailable */}
        <img
          src={geemAvatarUrl()}
          alt={alt}
          className="h-full w-full max-h-full max-w-full object-contain"
        />
      </object>
    </span>
  );
}
