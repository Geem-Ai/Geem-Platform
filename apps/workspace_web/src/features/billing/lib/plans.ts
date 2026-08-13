import type { PurchasablePlan } from '@/services/api/billing';
import { compareMoneyAmount } from './money';

/** Current plan first, then price, then name. No upgrade/downgrade hierarchy. */
export function sortPlansForDisplay(
  plans: readonly PurchasablePlan[],
  currentPlanId?: string,
): PurchasablePlan[] {
  return [...plans].sort((a, b) => {
    if (currentPlanId) {
      if (a.id === currentPlanId) return -1;
      if (b.id === currentPlanId) return 1;
    }
    const byPrice = compareMoneyAmount(a.price_amount, b.price_amount);
    if (byPrice !== 0) return byPrice;
    return a.name.localeCompare(b.name);
  });
}
