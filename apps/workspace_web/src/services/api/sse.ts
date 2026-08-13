import { ApiError, isKnownApiErrorCode, type ApiErrorCode } from './errors';
import { buildHeaders, getApiBaseUrl, parseError } from './client';

export type SseHandlers = {
  onEvent?: (event: string, data: unknown) => void;
  onError?: (message: string, code?: ApiErrorCode) => void;
};

function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = 'message';
  const dataLines: string[] = [];

  for (const rawLine of block.split('\n')) {
    const line = rawLine.replace(/\r$/, '');
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) return null;
  return { event, data: dataLines.join('\n') };
}

/**
 * Generic SSE POST reader adapted from the MVP `apps/web` client.
 * Domain chat wiring belongs in later phases.
 */
export async function streamSse(
  path: string,
  body: unknown,
  handlers: SseHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers = buildHeaders({
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  });

  let res: Response;
  try {
    res = await fetch(`${getApiBaseUrl()}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      throw new ApiError('Request aborted', { status: 0, code: 'aborted' });
    }
    throw new ApiError(err instanceof Error ? err.message : 'Network error', {
      status: 0,
      code: 'network',
    });
  }

  if (!res.ok) {
    throw await parseError(res);
  }

  if (!res.body) {
    throw new ApiError('Streaming is not supported in this browser', {
      status: 0,
      code: 'unknown',
    });
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const parsed = parseSseBlock(block);
      if (!parsed) continue;

      let payload: unknown = parsed.data;
      try {
        payload = JSON.parse(parsed.data);
      } catch {
        /* keep raw string */
      }

      if (parsed.event === 'error') {
        const obj =
          typeof payload === 'object' && payload !== null
            ? (payload as Record<string, unknown>)
            : {};
        const message =
          typeof obj.message === 'string' ? obj.message : 'Stream error';
        const rawCode = obj.error ?? obj.code;
        const code: ApiErrorCode = isKnownApiErrorCode(rawCode)
          ? rawCode
          : 'unknown';
        handlers.onEvent?.(parsed.event, payload);
        handlers.onError?.(message, code);
        throw new ApiError(message, { status: 0, code });
      }

      handlers.onEvent?.(parsed.event, payload);
    }
  }
}
