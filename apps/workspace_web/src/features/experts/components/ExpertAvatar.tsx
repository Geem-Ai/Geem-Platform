import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

type ExpertAvatarProps = {
  name: string;
  iconUrl?: string | null;
  ownership?: 'workspace' | 'platform';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
};

const sizeClass = {
  sm: 'size-9 text-sm',
  md: 'size-11 text-base',
  lg: 'size-12 text-lg',
} as const;

const iconSizeClass = {
  sm: 'size-4',
  md: 'size-5',
  lg: 'size-5',
} as const;

export function ExpertAvatar({
  name,
  iconUrl,
  ownership = 'workspace',
  size = 'md',
  className,
}: ExpertAvatarProps) {
  if (iconUrl) {
    return (
      <img
        src={iconUrl}
        alt=""
        className={cn(
          'rounded-xl shrink-0 object-cover border border-border',
          sizeClass[size],
          className,
        )}
      />
    );
  }

  const initial = name.trim().charAt(0).toUpperCase() || '?';

  return (
    <div
      className={cn(
        'rounded-xl shrink-0 border border-border flex items-center justify-center font-semibold',
        ownership === 'platform'
          ? 'bg-primary/10 text-primary'
          : 'bg-muted text-foreground/80',
        sizeClass[size],
        className,
      )}
      aria-hidden
    >
      {ownership === 'platform' ? (
        <Sparkles className={iconSizeClass[size]} />
      ) : (
        initial
      )}
    </div>
  );
}
