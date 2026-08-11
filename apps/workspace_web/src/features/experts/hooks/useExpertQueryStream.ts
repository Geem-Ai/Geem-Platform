import { useCallback, useEffect, useRef, useState } from 'react';
import type { Citation } from '@/services/api/types';
import { queryExpertStream } from '@/services/api/query';
import { ApiError, type ApiErrorCode } from '@/services/api/errors';

export type StreamState = {
  isStreaming: boolean;
  answer: string;
  citations: Citation[];
  error: string | null;
  errorCode: ApiErrorCode | null;
  insufficientContext: boolean;
};

const INITIAL_STATE: StreamState = {
  isStreaming: false,
  answer: '',
  citations: [],
  error: null,
  errorCode: null,
  insufficientContext: false,
};

function textFromPayload(data: unknown): string {
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (typeof obj.text === 'string') return obj.text;
    if (typeof obj.token === 'string') return obj.token;
  }
  return '';
}

export function useExpertQueryStream(workspaceId: string) {
  const [state, setState] = useState<StreamState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  /** Clear state when workspace changes. */
  useEffect(() => {
    abort();
    setState(INITIAL_STATE);
  }, [workspaceId, abort]);

  const ask = useCallback(
    async (question: string, expertId: string) => {
      abort();

      const controller = new AbortController();
      abortRef.current = controller;

      setState({
        isStreaming: true,
        answer: '',
        citations: [],
        error: null,
        errorCode: null,
        insufficientContext: false,
      });

      let accumulated = '';

      try {
        await queryExpertStream(
          question,
          expertId,
          {
            onEvent(event, data) {
              if (event === 'token' || event === 'message') {
                accumulated += textFromPayload(data);
                setState((s) => ({ ...s, answer: accumulated }));
              } else if (event === 'replace') {
                accumulated = textFromPayload(data);
                setState((s) => ({ ...s, answer: accumulated }));
              } else if (event === 'citations') {
                const items = Array.isArray(data) ? (data as Citation[]) : [];
                setState((s) => ({ ...s, citations: items }));
              } else if (event === 'final' || event === 'done' || event === 'end') {
                const payload = data as Record<string, unknown> | null;
                if (payload && typeof payload === 'object') {
                  if (typeof payload.answer === 'string') {
                    accumulated = payload.answer;
                  }
                  setState((s) => ({
                    ...s,
                    answer: accumulated,
                    citations: Array.isArray(payload.citations)
                      ? (payload.citations as Citation[])
                      : s.citations,
                    insufficientContext: Boolean(payload.insufficient_context),
                  }));
                }
              }
            },
            onError(message) {
              setState((s) => ({
                ...s,
                isStreaming: false,
                error: message,
                errorCode: 'unknown',
              }));
            },
          },
          controller.signal,
        );
      } catch (err) {
        if (err instanceof ApiError && err.code === 'aborted') {
          return;
        }
        if (err instanceof ApiError) {
          setState((s) => ({
            ...s,
            error: err.message,
            errorCode: err.code,
          }));
          return;
        }
        const message = err instanceof Error ? err.message : 'Unknown error';
        setState((s) => ({ ...s, error: message, errorCode: 'unknown' }));
      } finally {
        setState((s) => ({ ...s, isStreaming: false }));
      }
    },
    [abort],
  );

  const clear = useCallback(() => {
    abort();
    setState(INITIAL_STATE);
  }, [abort]);

  return { ...state, ask, clear, abort };
}
