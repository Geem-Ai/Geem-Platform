export function publicChatCurlExample(apiBaseUrl: string): string {
  const base = (apiBaseUrl || '').replace(/\/$/, '');
  return `curl -X POST "${base}/api/v1/chat/completions" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "X-Geem-Expert-Id: YOUR_EXPERT_ID" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "geem",
    "messages": [{"role": "user", "content": "Hello Geem"}],
    "stream": false
  }'`;
}

export function publicChatStreamBodyExample(): string {
  return `{
  "model": "geem",
  "messages": [{"role": "user", "content": "Hello Geem"}],
  "stream": true
}`;
}
