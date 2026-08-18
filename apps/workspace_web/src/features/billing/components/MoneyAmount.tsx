import { cn } from '@/lib/utils';
import { formatMoney, normalizeMoneyCurrency, normalizeMoneyValue } from '../lib/money';
import { SaudiRiyalSymbol } from './SaudiRiyalSymbol';

type MoneyAmountProps = {
  amount: string;
  currency: string;
  className?: string;
  /** Icon size relative to surrounding text (default matches body/price lines). */
  iconClassName?: string;
};

/** Renders a money amount; SAR uses the official riyal SVG instead of the letters "SAR". */
export function MoneyAmount({
  amount,
  currency,
  className,
  iconClassName,
}: MoneyAmountProps) {
  const code = normalizeMoneyCurrency(currency);
  const value = normalizeMoneyValue(amount);
  const label = formatMoney(amount, currency);

  if (code === 'SAR') {
    return (
      <span
        className={cn('inline-flex items-center gap-1 whitespace-nowrap', className)}
        aria-label={label}
        data-currency="SAR"
      >
        <SaudiRiyalSymbol
          className={cn('h-[0.85em] w-[0.76em] translate-y-px', iconClassName)}
        />
        <span className="tabular-nums">{value}</span>
      </span>
    );
  }

  return (
    <span
      className={cn('inline-flex items-center gap-1 whitespace-nowrap tabular-nums', className)}
      aria-label={label}
      data-currency={code}
    >
      {code} {value}
    </span>
  );
}
