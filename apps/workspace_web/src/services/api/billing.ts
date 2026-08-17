import { apiRequest } from './client';

export type BillingEntitlement = {
  key: string;
  value: number | boolean | string;
  value_type: string;
};

export type PurchasablePlan = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: string;
  price_amount: string;
  currency: string;
  entitlements: BillingEntitlement[];
};

export type CreditPack = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  credits: number;
  price_amount: string;
  currency: string;
  active: boolean;
};

export type CheckoutResult = {
  purchase_id: string;
  status: string;
  kind: string;
  amount: string;
  currency: string;
  redirect_url: string;
};

export type PurchaseKind = 'subscription' | 'credit_pack' | string;

export type PurchaseStatus =
  | 'pending'
  | 'redirected'
  | 'paid'
  | 'failed'
  | 'cancelled'
  | 'expired'
  | string;

export type Purchase = {
  id: string;
  status: PurchaseStatus;
  kind: PurchaseKind;
  amount: string;
  currency: string;
  item_name: string | null;
  item_code: string | null;
  credits: number | null;
  app_slug?: string | null;
  app_name?: string | null;
  commercial_action?: string | null;
  billing_interval?: string | null;
  paid_at: string | null;
  created_at: string;
};

export const BILLING_HISTORY_PAGE_SIZE = 25;

export type PurchaseList = {
  items: Purchase[];
  total: number;
  limit: number;
  offset: number;
};

export function listBillingPlans(): Promise<PurchasablePlan[]> {
  return apiRequest<PurchasablePlan[]>('/api/billing/plans');
}

export function listCreditPacks(): Promise<CreditPack[]> {
  return apiRequest<CreditPack[]>('/api/billing/credit-packs');
}

export function createSubscriptionCheckout(planId: string): Promise<CheckoutResult> {
  return apiRequest<CheckoutResult>('/api/billing/checkout/subscription', {
    method: 'POST',
    json: { plan_id: planId },
  });
}

export function createCreditPackCheckout(packId: string): Promise<CheckoutResult> {
  return apiRequest<CheckoutResult>('/api/billing/checkout/credit-packs', {
    method: 'POST',
    json: { credit_pack_id: packId },
  });
}

export function getPurchase(purchaseId: string): Promise<Purchase> {
  return apiRequest<Purchase>(`/api/billing/purchases/${purchaseId}`);
}

export function listPurchases(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  kind?: string;
}): Promise<PurchaseList> {
  const qs = new URLSearchParams();
  qs.set('limit', String(params?.limit ?? BILLING_HISTORY_PAGE_SIZE));
  qs.set('offset', String(params?.offset ?? 0));
  if (params?.status && params.status !== 'all') qs.set('status', params.status);
  if (params?.kind && params.kind !== 'all') qs.set('kind', params.kind);
  return apiRequest<PurchaseList>(`/api/billing/purchases?${qs.toString()}`);
}
