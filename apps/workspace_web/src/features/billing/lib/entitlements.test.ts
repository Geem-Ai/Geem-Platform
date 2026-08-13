import { describe, expect, it } from 'vitest';
import { sortEntitlements } from './entitlements';

describe('sortEntitlements', () => {
  it('orders AI token windows daily → weekly → monthly', () => {
    const ordered = sortEntitlements([
      { key: 'ai_tokens_monthly' },
      { key: 'storage_bytes' },
      { key: 'ai_tokens_daily' },
      { key: 'experts_limit' },
      { key: 'ai_tokens_weekly' },
    ]);
    expect(ordered.map((item) => item.key)).toEqual([
      'ai_tokens_daily',
      'ai_tokens_weekly',
      'ai_tokens_monthly',
      'experts_limit',
      'storage_bytes',
    ]);
  });
});
