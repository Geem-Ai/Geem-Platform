import { Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

type InfoTooltipProps = {
  label: string;
  content: string;
};

export function InfoTooltip({ label, content }: InfoTooltipProps) {
  const { t } = useTranslation();

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={t('common.moreInfoAbout', { label })}
        >
          <Info className="size-3" strokeWidth={2.25} aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent
        variant="light"
        side="top"
        align="center"
        className="max-w-[17.5rem] px-3 py-2.5"
      >
        <div className="space-y-1 text-start">
          <p className="text-xs font-medium text-foreground">{label}</p>
          <p className="text-xs leading-relaxed text-muted-foreground">{content}</p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
