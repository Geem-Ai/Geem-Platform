export type ApiErrorCode =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'quota_exceeded'
  | 'billing_required'
  | 'network'
  | 'aborted'
  | 'unknown';

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly details?: unknown;

  constructor(
    message: string,
    options: { status: number; code: ApiErrorCode; details?: unknown },
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
  }
}

export function mapStatusToCode(status: number, body?: Record<string, unknown>): ApiErrorCode {
  const explicit = typeof body?.code === 'string' ? body.code : undefined;
  if (explicit === 'quota_exceeded') return 'quota_exceeded';
  if (explicit === 'billing_required') return 'billing_required';

  switch (status) {
    case 401:
      return 'unauthorized';
    case 403:
      return 'forbidden';
    case 404:
      return 'not_found';
    case 409:
      return 'conflict';
    case 422:
      return 'validation';
    case 402:
      return 'billing_required';
    case 429:
      return 'quota_exceeded';
    default:
      return 'unknown';
  }
}
