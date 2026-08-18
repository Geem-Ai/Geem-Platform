import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import type { CreditPack } from '@/services/api/billing';
import { formatCount } from '@/features/usage/lib/quota';
import { MoneyAmount } from './MoneyAmount';

export function CreditPackCard({
  pack,
  checkoutDisabled,
  checkoutPending,
  onBuy,
}: {
  pack: CreditPack;
  checkoutDisabled?: boolean;
  checkoutPending?: boolean;
  onBuy: (pack: CreditPack) => void;
}) {
  const { t, i18n } = useTranslation();

  return (
    <Card data-testid={`billing-pack-${pack.id}`} className="shadow-xs h-full">
      <CardContent className="p-5 sm:p-6 flex flex-col gap-4 h-full">
        <div className="space-y-2 min-w-0 flex-1">
          <h3 className="text-base font-semibold tracking-tight">{pack.name}</h3>
          {pack.description ? (
            <p className="text-sm text-muted-foreground leading-relaxed">
              {pack.description}
            </p>
          ) : null}
          <p className="text-sm text-muted-foreground">
            {t('billing.packCredits', {
              count: formatCount(pack.credits, i18n.language),
            })}
          </p>
          <p className="text-xl font-semibold tracking-tight">
            <MoneyAmount amount={pack.price_amount} currency={pack.currency} />
          </p>
        </div>
        <Button
          type="button"
          onClick={() => onBuy(pack)}
          disabled={checkoutDisabled || checkoutPending}
          data-testid="billing-pack-cta"
        >
          {t('billing.buyPack')}
        </Button>
      </CardContent>
    </Card>
  );
}
