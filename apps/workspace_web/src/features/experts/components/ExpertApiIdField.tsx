import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { copyText } from '@/lib/clipboard';

export function ExpertApiIdField({ expertId }: { expertId: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    const ok = await copyText(expertId);
    if (ok) {
      setCopied(true);
      toast.success(t('experts.apiIdCopied'));
    } else {
      toast.error(t('apiKeys.copyFailed'));
    }
  }

  return (
    <div className="space-y-2" data-testid="expert-api-id">
      <p className="text-xs font-medium text-muted-foreground">{t('experts.apiId')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <code dir="ltr" className="text-xs font-mono break-all">
          {expertId}
        </code>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void handleCopy()}
          data-testid="copy-expert-api-id"
        >
          {copied ? t('apiKeys.copied') : t('experts.copyApiId')}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('experts.apiIdHint')}</p>
    </div>
  );
}
