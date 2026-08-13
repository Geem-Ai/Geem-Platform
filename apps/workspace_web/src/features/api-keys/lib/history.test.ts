import { describe, expect, it } from 'vitest';
import { apiUsageDayBucket, groupApiUsageByDay } from './history';

describe('api usage history helpers', () => {
  it('buckets timestamps into today / yesterday / other', () => {
    const now = new Date(2026, 7, 13, 15, 0, 0);
    expect(apiUsageDayBucket(new Date(2026, 7, 13, 10, 0, 0).toISOString(), now)).toBe(
      'today',
    );
    expect(apiUsageDayBucket(new Date(2026, 7, 12, 10, 0, 0).toISOString(), now)).toBe(
      'yesterday',
    );
    expect(apiUsageDayBucket(new Date(2026, 7, 1, 10, 0, 0).toISOString(), now)).toBe(
      'other',
    );
  });

  it('groups events in first-seen day order', () => {
    const groups = groupApiUsageByDay([
      { id: 'a', created_at: '2026-08-13T10:00:00Z' },
      { id: 'b', created_at: '2026-08-12T09:00:00Z' },
      { id: 'c', created_at: '2026-08-13T11:00:00Z' },
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0]?.items.map((item) => item.id)).toEqual(['a', 'c']);
    expect(groups[1]?.items.map((item) => item.id)).toEqual(['b']);
  });
});
