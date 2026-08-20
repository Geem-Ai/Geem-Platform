export type ApiErrorCode =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'rate_limited'
  | 'invalid_credentials'
  | 'email_already_exists'
  | 'session_expired'
  | 'session_revoked'
  | 'email_not_verified'
  | 'network'
  | 'aborted'
  | 'platform_admin_required'
  | 'platform_admin_host_required'
  | 'unknown';

const KNOWN_CODES = new Set<string>([
  'unauthorized',
  'forbidden',
  'not_found',
  'conflict',
  'validation',
  'rate_limited',
  'invalid_credentials',
  'email_already_exists',
  'session_expired',
  'session_revoked',
  'email_not_verified',
  'platform_admin_required',
  'platform_admin_host_required',
]);

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

export function isKnownApiErrorCode(value: unknown): value is ApiErrorCode {
  return typeof value === 'string' && KNOWN_CODES.has(value);
}

export function mapStatusToCode(
  status: number,
  body?: Record<string, unknown>,
): ApiErrorCode {
  const explicit =
    (typeof body?.code === 'string' && body.code) ||
    (typeof body?.error === 'string' && body.error) ||
    undefined;
  if (isKnownApiErrorCode(explicit)) {
    return explicit;
  }

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
    case 429:
      return 'rate_limited';
    default:
      return 'unknown';
  }
}

export function errorMessageKey(code: string): string {
  const map: Partial<Record<ApiErrorCode, string>> = {
    invalid_credentials: 'errors.invalidCredentials',
    session_expired: 'errors.sessionExpired',
    session_revoked: 'errors.sessionExpired',
    unauthorized: 'errors.sessionExpired',
    email_not_verified: 'errors.emailNotVerified',
    rate_limited: 'errors.rateLimited',
    network: 'errors.network',
    validation: 'errors.validation',
    forbidden: 'errors.forbidden',
    not_found: 'errors.notFound',
    platform_admin_required: 'errors.platformAdminRequired',
    platform_admin_host_required: 'errors.platformAdminHostRequired',
  };
  return map[code as ApiErrorCode] ?? 'errors.generic';
}
