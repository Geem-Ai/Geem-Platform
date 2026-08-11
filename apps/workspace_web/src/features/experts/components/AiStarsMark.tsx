import { cn } from '@/lib/utils';

type AiStarsMarkProps = {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
};

const sizeClass = {
  sm: 'size-9',
  md: 'size-11',
  lg: 'size-12',
} as const;

function Star({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="currentColor"
      aria-hidden
    >
      <path d="M12 1.5 14.1 8.7 21.5 10.9 14.1 13.1 12 20.3 9.9 13.1 2.5 10.9 9.9 8.7Z" />
    </svg>
  );
}

/**
 * Expert card AI mark — small constellation with restrained orbital motion.
 */
export function AiStarsMark({ size = 'md', className }: AiStarsMarkProps) {
  return (
    <div
      className={cn(
        'relative shrink-0 overflow-hidden rounded-xl',
        'border border-border/80 bg-muted/80 text-muted-foreground',
        'transition-colors duration-200',
        'group-hover:border-primary/20 group-hover:bg-primary/5 group-hover:text-primary',
        sizeClass[size],
        className,
      )}
      aria-hidden
    >
      <Star className="ai-star ai-star-orbit-a absolute start-[18%] top-[22%] size-[38%]" />
      <Star className="ai-star ai-star-orbit-b absolute end-[14%] top-[16%] size-[24%] opacity-80" />
      <Star className="ai-star ai-star-orbit-c absolute end-[22%] bottom-[16%] size-[18%] opacity-70" />
    </div>
  );
}
