import { describe, expect, it } from 'vitest';
import type { UsageHistoryItem } from '@/services/api/usage';
import {
  creditDeltaSign,
  groupHistoryByDay,
  historyDayBucket,
  historyKindLabelKey,
  historyPageHref,
  isKnownHistoryKind,
  matchDatePreset,
  operationLabelKey,
  parseHistoryKind,
  presetDateRange,
  shortenId,
} from './history';

function item(id: string, createdAt: string): UsageHistoryItem {
  return {
    id,
    kind: 'ai_tokens',
    tokens: 1,
    credits: null,
    created_at: createdAt,
  };
}

describe('usage history helpers', () => {
  it('parses kind filters from the query string', () => {
    expect(parseHistoryKind(null)).toBe('all');
    expect(parseHistoryKind('ai')).toBe('ai');
    expect(parseHistoryKind('ai_tokens')).toBe('ai');
    expect(parseHistoryKind('credits')).toBe('credits');
    expect(parseHistoryKind('nope')).toBe('all');
  });

  it('labels OpenRouter families as distinct history kinds', () => {
    expect(isKnownHistoryKind('chat_tokens')).toBe(true);
    expect(isKnownHistoryKind('embed_tokens')).toBe(true);
    expect(isKnownHistoryKind('rerank_tokens')).toBe(true);
    expect(isKnownHistoryKind('ocr_tokens')).toBe(true);
    expect(isKnownHistoryKind('title_tokens')).toBe(true);
    expect(isKnownHistoryKind('stt_tokens')).toBe(true);
    expect(historyKindLabelKey('embed_tokens')).toBe('usage.kind.embed_tokens');
    expect(historyKindLabelKey('ocr_tokens')).toBe('usage.kind.ocr_tokens');
    expect(historyKindLabelKey('stt_tokens')).toBe('usage.kind.stt_tokens');
    expect(operationLabelKey('speech_to_text')).toBe('usage.operation.speech_to_text');
  });

  it('keeps kind in paginated history URLs', () => {
    expect(historyPageHref(1)).toBe('/billing/usage/history');
    expect(historyPageHref(2)).toBe('/billing/usage/history?page=2');
    expect(historyPageHref(1, 'ai')).toBe('/billing/usage/history?kind=ai');
    expect(historyPageHref(3, 'credits')).toBe(
      '/billing/usage/history?page=3&kind=credits',
    );
    expect(historyPageHref(1, 'ai', { from: '2026-08-01', to: '2026-08-13' })).toBe(
      '/billing/usage/history?kind=ai&from=2026-08-01&to=2026-08-13',
    );
  });

  it('matches date presets from local from/to keys', () => {
    const now = new Date(2026, 7, 13, 18, 0, 0);
    expect(matchDatePreset({}, now)).toBe('all');
    expect(matchDatePreset(presetDateRange('today', now), now)).toBe('today');
    expect(matchDatePreset(presetDateRange('7d', now), now)).toBe('7d');
    expect(matchDatePreset({ from: '2026-08-01', to: '2026-08-13' }, now)).toBe(
      'custom',
    );
  });

  it('signs credit consume and expiry as decreases', () => {
    expect(creditDeltaSign('credit_grant')).toBe(1);
    expect(creditDeltaSign('credit_consume')).toBe(-1);
    expect(creditDeltaSign('credit_expire')).toBe(-1);
  });

  it('groups consecutive items that share a local calendar day', () => {
    const groups = groupHistoryByDay([
      item('a', '2026-08-13T10:00:00'),
      item('b', '2026-08-13T18:00:00'),
      item('c', '2026-08-12T09:00:00'),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0]?.items.map((row) => row.id)).toEqual(['a', 'b']);
    expect(groups[1]?.items.map((row) => row.id)).toEqual(['c']);
  });

  it('labels today and yesterday relative to a fixed now', () => {
    const now = new Date(2026, 7, 13, 18, 0, 0);
    expect(historyDayBucket('2026-08-13T10:00:00', now)).toBe('today');
    expect(historyDayBucket('2026-08-12T10:00:00', now)).toBe('yesterday');
    expect(historyDayBucket('2026-08-01T10:00:00', now)).toBe('other');
  });

  it('shortens ids for audit display', () => {
    expect(shortenId('a1b2c3d4-e5f6-7890-abcd-ef1234567890')).toBe('a1b2c3d4');
  });
});
