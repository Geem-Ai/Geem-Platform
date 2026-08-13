export type ApiErrorCode =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'quota_exceeded'
  | 'insufficient_credits'
  | 'expert_limit_reached'
  | 'storage_quota_exceeded'
  | 'billing_required'
  | 'rate_limited'
  | 'invalid_credentials'
  | 'email_already_exists'
  | 'session_expired'
  | 'session_revoked'
  | 'weak_password'
  | 'workspace_slug_taken'
  | 'workspace_slug_invalid'
  | 'workspace_not_found'
  | 'membership_not_found'
  | 'workspace_access_denied'
  | 'insufficient_workspace_role'
  | 'last_workspace_owner'
  | 'document_not_found'
  | 'document_already_exists'
  | 'document_deleted'
  | 'invalid_document'
  | 'unsupported_document_type'
  | 'expert_not_found'
  | 'expert_access_denied'
  | 'expert_immutable'
  | 'expert_not_ready'
  | 'expert_disabled'
  | 'expert_has_no_knowledge'
  | 'expert_knowledge_unavailable'
  | 'upload_type_rejected'
  | 'upload_too_large'
  | 'conversation_not_found'
  | 'message_not_found'
  | 'conversation_busy'
  | 'generation_failed'
  | 'network'
  | 'aborted'
  | 'unknown';

const KNOWN_CODES = new Set<string>([
  'unauthorized',
  'forbidden',
  'not_found',
  'conflict',
  'validation',
  'quota_exceeded',
  'insufficient_credits',
  'expert_limit_reached',
  'storage_quota_exceeded',
  'billing_required',
  'rate_limited',
  'invalid_credentials',
  'email_already_exists',
  'session_expired',
  'session_revoked',
  'weak_password',
  'workspace_slug_taken',
  'workspace_slug_invalid',
  'workspace_not_found',
  'membership_not_found',
  'workspace_access_denied',
  'insufficient_workspace_role',
  'last_workspace_owner',
  'document_not_found',
  'document_already_exists',
  'document_deleted',
  'invalid_document',
  'unsupported_document_type',
  'expert_not_found',
  'expert_access_denied',
  'expert_immutable',
  'expert_not_ready',
  'expert_disabled',
  'expert_has_no_knowledge',
  'expert_knowledge_unavailable',
  'upload_type_rejected',
  'upload_too_large',
  'conversation_not_found',
  'message_not_found',
  'conversation_busy',
  'generation_failed',
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

export function mapStatusToCode(status: number, body?: Record<string, unknown>): ApiErrorCode {
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
    case 402:
      return 'billing_required';
    case 429:
      return 'rate_limited';
    default:
      return 'unknown';
  }
}

/** Map stable backend codes to i18n keys under `errors.*`. */
export function errorMessageKey(code: ApiErrorCode): string {
  const map: Partial<Record<ApiErrorCode, string>> = {
    invalid_credentials: 'errors.invalidCredentials',
    email_already_exists: 'errors.emailAlreadyExists',
    session_expired: 'errors.sessionExpired',
    session_revoked: 'errors.sessionExpired',
    unauthorized: 'errors.sessionExpired',
    weak_password: 'errors.weakPassword',
    workspace_slug_taken: 'errors.workspaceSlugTaken',
    workspace_slug_invalid: 'errors.workspaceSlugInvalid',
    workspace_not_found: 'errors.workspaceNotFound',
    workspace_access_denied: 'errors.workspaceAccessDenied',
    insufficient_workspace_role: 'errors.insufficientRole',
    last_workspace_owner: 'errors.lastWorkspaceOwner',
    rate_limited: 'errors.rateLimited',
    network: 'errors.network',
    validation: 'errors.validation',
    conflict: 'errors.conflict',
    forbidden: 'errors.forbidden',
    not_found: 'errors.notFound',
    document_not_found: 'errors.documentNotFound',
    document_already_exists: 'errors.documentAlreadyExists',
    document_deleted: 'errors.documentDeleted',
    invalid_document: 'errors.invalidDocument',
    unsupported_document_type: 'errors.unsupportedDocumentType',
    expert_not_found: 'errors.expertNotFound',
    expert_access_denied: 'errors.expertAccessDenied',
    expert_immutable: 'errors.expertImmutable',
    expert_not_ready: 'errors.expertNotReady',
    expert_disabled: 'errors.expertDisabled',
    expert_has_no_knowledge: 'errors.expertHasNoKnowledge',
    expert_knowledge_unavailable: 'errors.expertKnowledgeUnavailable',
    upload_type_rejected: 'errors.uploadTypeRejected',
    upload_too_large: 'errors.uploadTooLarge',
    conversation_not_found: 'errors.conversationNotFound',
    message_not_found: 'errors.messageNotFound',
    conversation_busy: 'errors.conversationBusy',
    generation_failed: 'errors.generationFailed',
    quota_exceeded: 'errors.quotaExceeded',
    insufficient_credits: 'errors.insufficientCredits',
    expert_limit_reached: 'errors.expertLimitReached',
    storage_quota_exceeded: 'errors.storageQuotaExceeded',
  };
  return map[code] ?? 'errors.generic';
}

export function isQuotaErrorCode(code: string | null | undefined): boolean {
  return (
    code === 'quota_exceeded' ||
    code === 'insufficient_credits' ||
    code === 'expert_limit_reached' ||
    code === 'storage_quota_exceeded'
  );
}
