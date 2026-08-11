import { describe, expect, it } from 'vitest';
import type { ExpertKnowledgeItem } from '@/services/api/types';
import { POLL_INTERVAL_MS, shouldPollExpert, shouldPollKnowledge } from './polling';

function makeItem(status: string): ExpertKnowledgeItem {
  return {
    id: '1',
    expert_id: 'e1',
    document_id: 'd1',
    source_id: null,
    created_at: '',
    title: 'Test',
    original_filename: 'test.pdf',
    status,
    mime_type: 'application/pdf',
    byte_size: 1000,
    page_count: 1,
    failure_reason: null,
    source_type: 'upload',
  };
}

describe('POLL_INTERVAL_MS', () => {
  it('is 3000', () => {
    expect(POLL_INTERVAL_MS).toBe(3000);
  });
});

describe('shouldPollKnowledge', () => {
  it('returns true when any item is pending', () => {
    expect(shouldPollKnowledge([makeItem('pending')])).toBe(true);
  });
  it('returns true when any item is processing', () => {
    expect(shouldPollKnowledge([makeItem('ready'), makeItem('processing')])).toBe(true);
  });
  it('returns false when all items are ready or failed', () => {
    expect(shouldPollKnowledge([makeItem('ready'), makeItem('failed')])).toBe(false);
  });
  it('returns false for empty list', () => {
    expect(shouldPollKnowledge([])).toBe(false);
  });
});

describe('shouldPollExpert', () => {
  it('returns true for processing and draft', () => {
    expect(shouldPollExpert('processing')).toBe(true);
    expect(shouldPollExpert('draft')).toBe(true);
  });
  it('returns false for terminal statuses', () => {
    expect(shouldPollExpert('ready')).toBe(false);
    expect(shouldPollExpert('failed')).toBe(false);
    expect(shouldPollExpert('disabled')).toBe(false);
  });
});
