import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { copyText } from '@/lib/clipboard';
import { cn } from '@/lib/utils';

type CopyableCodeBlockProps = {
  code: string;
  testId?: string;
  className?: string;
};

export function CopyableCodeBlock({
  code,
  testId,
  className,
}: CopyableCodeBlockProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    const ok = await copyText(code);
    if (!ok) {
      toast.error(t('apiKeys.copyFailed'));
      return;
    }
    setCopied(true);
    toast.success(t('apiKeys.copied'));
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className={cn('relative group min-w-0 max-w-full', className)}>
      <pre
        dir="ltr"
        className="max-w-full overflow-x-auto rounded-md border border-border bg-muted/40 p-3 pe-11 text-xs font-mono whitespace-pre-wrap break-all"
        data-testid={testId}
      >
        {code}
      </pre>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            mode="icon"
            variant="outline"
            size="sm"
            className="absolute top-2 end-2 size-7 bg-background/90 shadow-xs"
            onClick={() => void handleCopy()}
            aria-label={copied ? t('apiKeys.copied') : t('apiKeys.copySnippet')}
            data-testid={testId ? `${testId}-copy` : undefined}
          >
            {copied ? (
              <Check className="size-3.5 text-[var(--color-success-accent,var(--color-green-600))]" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">
          {copied ? t('apiKeys.copied') : t('apiKeys.copySnippet')}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
