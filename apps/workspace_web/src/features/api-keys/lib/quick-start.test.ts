import { describe, expect, it } from 'vitest';
import { publicChatCurlExample, publicChatStreamBodyExample } from './quick-start';

describe('public Chat quick start', () => {
  it('builds a POST /api/v1/chat/completions curl with placeholders', () => {
    const snippet = publicChatCurlExample('https://api.geem.ai/');
    expect(snippet).toContain('POST "https://api.geem.ai/api/v1/chat/completions"');
    expect(snippet).toContain('Authorization: Bearer YOUR_API_KEY');
    expect(snippet).toContain('X-Geem-Expert-Id: YOUR_EXPERT_ID');
    expect(snippet).toContain('"model": "geem"');
    expect(snippet).toContain('"stream": false');
    expect(snippet).not.toContain('expert_id');
    expect(snippet).not.toContain('geem_sk_');
    expect(snippet).not.toContain('localhost');
  });

  it('explains OpenAI SSE via stream=true JSON', () => {
    const body = publicChatStreamBodyExample();
    expect(body).toContain('"stream": true');
    expect(body).toContain('"model": "geem"');
    expect(body).toContain('Hello Geem');
  });
});
