import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy, Info } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { copyText } from '@/lib/clipboard';

export function ExpertApiIdField({ expertId }: { expertId: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const apiIdLabel = t('experts.apiId');
  const apiIdHint = t('experts.apiIdHint');
  const copyLabel = copied ? t('apiKeys.copied') : t('experts.copyApiId');

  async function handleCopy() {
    const ok = await copyText(expertId);
    if (ok) {
      setCopied(true);
      toast.success(t('experts.apiIdCopied'));
      window.setTimeout(() => setCopied(false), 2000);
    } else {
      toast.error(t('apiKeys.copyFailed'));
    }
  }

  return (
    <div className="space-y-2" data-testid="expert-api-id">
      <div className="flex items-center gap-1.5">
        <p className="text-xs font-medium text-muted-foreground">{apiIdLabel}</p>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={t('common.moreInfoAbout', { label: apiIdLabel })}
              data-testid="expert-api-id-info"
            >
              <Info className="size-3" strokeWidth={2.25} aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent
            variant="light"
            side="top"
            align="start"
            className="max-w-[17.5rem] px-3 py-2.5"
          >
            <p className="text-xs leading-relaxed text-muted-foreground text-start">
              {apiIdHint}
            </p>
          </TooltipContent>
        </Tooltip>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <code dir="ltr" className="text-xs font-mono break-all">
          {expertId}
        </code>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              mode="icon"
              size="sm"
              variant="outline"
              className="size-7 shrink-0"
              onClick={() => void handleCopy()}
              aria-label={copyLabel}
              data-testid="copy-expert-api-id"
            >
              {copied ? (
                <Check
                  className="size-3.5 text-[var(--color-success-accent,var(--color-green-600))]"
                  aria-hidden
                />
              ) : (
                <Copy className="size-3.5" aria-hidden />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top">{copyLabel}</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
