import { Download, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { triggerBrowserDownload } from '@/lib/download';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { useDownloadPurchaseInvoice } from '../hooks/useBillingQueries';

export function DownloadInvoiceButton({ purchaseId }: { purchaseId: string }) {
  const { t } = useTranslation();
  const download = useDownloadPurchaseInvoice();
  const pending = download.isPending && download.variables === purchaseId;

  function handleClick() {
    download.mutate(purchaseId, {
      onSuccess: ({ blob, filename }) => {
        triggerBrowserDownload(blob, filename || `invoice-${purchaseId}.pdf`);
        toast.success(t('billing.invoiceDownloaded'));
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) {
          toast.error(t(errorMessageKey(err.code)));
        } else {
          toast.error(t('billing.invoiceDownloadFailed'));
        }
      },
    });
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleClick}
          disabled={pending}
          data-testid={`billing-invoice-download-${purchaseId}`}
          aria-label={t('billing.downloadInvoice')}
        >
          {pending ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <Download className="size-3.5" aria-hidden />
          )}
          {pending ? t('billing.downloadingInvoice') : t('billing.downloadInvoice')}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{t('billing.downloadInvoiceHint')}</TooltipContent>
    </Tooltip>
  );
}
