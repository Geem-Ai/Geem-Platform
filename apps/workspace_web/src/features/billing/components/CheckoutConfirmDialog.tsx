import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export type CheckoutConfirmRow = {
  label: string;
  value: string;
};

export function CheckoutConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  rows,
  features,
  pending,
  error,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  rows: CheckoutConfirmRow[];
  features?: CheckoutConfirmRow[];
  pending: boolean;
  error: unknown;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  const errorText =
    error instanceof ApiError
      ? t(errorMessageKey(error.code))
      : error
        ? t('errors.generic')
        : null;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!pending) onOpenChange(next);
      }}
    >
      <DialogContent data-testid="billing-checkout-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <dl className="space-y-3 text-sm">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-start justify-between gap-4"
            >
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd className="font-medium text-end">{row.value}</dd>
            </div>
          ))}
        </dl>
        {features && features.length > 0 ? (
          <div className="space-y-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
              {t('billing.includedAllowances')}
            </p>
            <ul className="space-y-1.5 text-sm">
              {features.map((item) => (
                <li key={item.label} className="flex items-start gap-2">
                  <Check className="size-4 text-primary mt-0.5 shrink-0" aria-hidden />
                  <span className="min-w-0 leading-5">
                    <span className="text-muted-foreground">{item.label}</span>
                    <span className="font-medium tabular-nums"> {item.value}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {errorText ? (
          <p className="text-sm text-destructive" data-testid="billing-checkout-error">
            {errorText}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            data-testid="billing-checkout-confirm"
          >
            {pending ? t('billing.redirecting') : t('billing.continueToPayment')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
