import { describe, expect, it } from 'vitest';
import { isChatWidgetApp } from '@/services/api/apps';

describe('chat widget helpers', () => {
  it('detects chat-widget catalog slug', () => {
    expect(isChatWidgetApp({ slug: 'chat-widget' })).toBe(true);
    expect(isChatWidgetApp({ slug: 'whatsapp' })).toBe(false);
    expect(isChatWidgetApp(null)).toBe(false);
  });
});
