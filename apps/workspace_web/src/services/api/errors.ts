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
  | 'unsupported_audio_type'
  | 'chat_attachment_not_found'
  | 'conversation_not_found'
  | 'message_not_found'
  | 'conversation_busy'
  | 'generation_failed'
  | 'network'
  | 'aborted'
  | 'billing_gateway_unavailable'
  | 'billing_gateway_error'
  | 'invalid_purchase'
  | 'purchase_not_found'
  | 'purchase_already_completed'
  | 'payment_verification_failed'
  | 'payment_amount_mismatch'
  | 'payment_currency_mismatch'
  | 'credit_pack_unavailable'
  | 'plan_unavailable'
  | 'system_workspace_checkout_forbidden'
  | 'app_not_found'
  | 'app_not_available'
  | 'app_already_installed'
  | 'app_not_installed'
  | 'app_billing_required'
  | 'app_install_forbidden'
  | 'app_installation_not_found'
  | 'app_plan_not_found'
  | 'app_plan_inactive'
  | 'app_plan_mismatch'
  | 'app_already_licensed'
  | 'app_subscription_required'
  | 'app_subscription_expired'
  | 'app_subscription_already_active'
  | 'app_renewal_not_allowed'
  | 'app_currency_not_supported'
  | 'app_checkout_forbidden'
  | 'app_checkout_in_progress'
  | 'app_purchase_not_payable'
  | 'connector_not_available'
  | 'connector_not_supported'
  | 'connector_limit_reached'
  | 'connector_not_found'
  | 'connector_already_disconnected'
  | 'connector_credentials_invalid'
  | 'connector_credentials_expired'
  | 'connector_connection_failed'
  | 'connector_health_check_failed'
  | 'connector_sync_not_supported'
  | 'connector_sync_in_progress'
  | 'connector_sync_not_found'
  | 'google_drive_not_configured'
  | 'google_drive_authorization_failed'
  | 'google_drive_reauthorization_required'
  | 'google_drive_file_not_found'
  | 'google_drive_file_access_denied'
  | 'google_drive_file_type_unsupported'
  | 'google_drive_export_too_large'
  | 'google_drive_download_failed'
  | 'google_drive_rate_limited'
  | 'google_drive_watch_failed'
  | 'google_drive_sync_failed'
  | 'microsoft_onedrive_not_configured'
  | 'microsoft_onedrive_authorization_failed'
  | 'microsoft_onedrive_reauthorization_required'
  | 'microsoft_onedrive_drive_not_supported'
  | 'microsoft_onedrive_item_not_found'
  | 'microsoft_onedrive_access_denied'
  | 'microsoft_onedrive_file_type_unsupported'
  | 'microsoft_onedrive_conversion_failed'
  | 'microsoft_onedrive_download_failed'
  | 'microsoft_onedrive_rate_limited'
  | 'microsoft_onedrive_delta_resync_required'
  | 'microsoft_onedrive_subscription_failed'
  | 'microsoft_onedrive_sync_failed'
  | 'openwa_not_configured'
  | 'openwa_unavailable'
  | 'openwa_unauthorized'
  | 'openwa_timeout'
  | 'openwa_request_invalid'
  | 'openwa_session_not_found'
  | 'openwa_session_conflict'
  | 'openwa_qr_not_ready'
  | 'openwa_pairing_failed'
  | 'openwa_phone_invalid'
  | 'openwa_webhook_failed'
  | 'openwa_send_failed'
  | 'channel_binding_required'
  | 'channel_expert_invalid'
  | 'api_key_not_found'
  | 'invitation_not_found'
  | 'invitation_already_exists'
  | 'already_workspace_member'
  | 'invalid_invitation'
  | 'invitation_expired'
  | 'invitation_revoked'
  | 'invitation_email_mismatch'
  | 'invitation_already_accepted'
  | 'email_delivery_failed'
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
  'unsupported_audio_type',
  'chat_attachment_not_found',
  'conversation_not_found',
  'message_not_found',
  'conversation_busy',
  'generation_failed',
  'billing_gateway_unavailable',
  'billing_gateway_error',
  'invalid_purchase',
  'purchase_not_found',
  'purchase_already_completed',
  'payment_verification_failed',
  'payment_amount_mismatch',
  'payment_currency_mismatch',
  'credit_pack_unavailable',
  'plan_unavailable',
  'system_workspace_checkout_forbidden',
  'app_not_found',
  'app_not_available',
  'app_already_installed',
  'app_not_installed',
  'app_billing_required',
  'app_install_forbidden',
  'app_installation_not_found',
  'app_plan_not_found',
  'app_plan_inactive',
  'app_plan_mismatch',
  'app_already_licensed',
  'app_subscription_required',
  'app_subscription_expired',
  'app_subscription_already_active',
  'app_renewal_not_allowed',
  'app_currency_not_supported',
  'app_checkout_forbidden',
  'app_checkout_in_progress',
  'app_purchase_not_payable',
  'connector_not_available',
  'connector_not_supported',
  'connector_limit_reached',
  'connector_not_found',
  'connector_already_disconnected',
  'connector_credentials_invalid',
  'connector_credentials_expired',
  'connector_connection_failed',
  'connector_health_check_failed',
  'connector_sync_not_supported',
  'connector_sync_in_progress',
  'connector_sync_not_found',
  'google_drive_not_configured',
  'google_drive_authorization_failed',
  'google_drive_reauthorization_required',
  'google_drive_file_not_found',
  'google_drive_file_access_denied',
  'google_drive_file_type_unsupported',
  'google_drive_export_too_large',
  'google_drive_download_failed',
  'google_drive_rate_limited',
  'google_drive_watch_failed',
  'google_drive_sync_failed',
  'microsoft_onedrive_not_configured',
  'microsoft_onedrive_authorization_failed',
  'microsoft_onedrive_reauthorization_required',
  'microsoft_onedrive_drive_not_supported',
  'microsoft_onedrive_item_not_found',
  'microsoft_onedrive_access_denied',
  'microsoft_onedrive_file_type_unsupported',
  'microsoft_onedrive_conversion_failed',
  'microsoft_onedrive_download_failed',
  'microsoft_onedrive_rate_limited',
  'microsoft_onedrive_delta_resync_required',
  'microsoft_onedrive_subscription_failed',
  'microsoft_onedrive_sync_failed',
  'openwa_not_configured',
  'openwa_unavailable',
  'openwa_unauthorized',
  'openwa_timeout',
  'openwa_request_invalid',
  'openwa_session_not_found',
  'openwa_session_conflict',
  'openwa_qr_not_ready',
  'openwa_pairing_failed',
  'openwa_phone_invalid',
  'openwa_webhook_failed',
  'openwa_send_failed',
  'channel_binding_required',
  'channel_expert_invalid',
  'api_key_not_found',
  'invitation_not_found',
  'invitation_already_exists',
  'already_workspace_member',
  'invalid_invitation',
  'invitation_expired',
  'invitation_revoked',
  'invitation_email_mismatch',
  'invitation_already_accepted',
  'email_delivery_failed',
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
    case 413:
      return 'upload_too_large';
    case 429:
      return 'rate_limited';
    default:
      return 'unknown';
  }
}

/** Map stable backend codes to i18n keys under `errors.*`. */
export function errorMessageKey(code: string): string {
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
    unsupported_audio_type: 'errors.unsupportedAudioType',
    chat_attachment_not_found: 'errors.chatAttachmentNotFound',
    conversation_not_found: 'errors.conversationNotFound',
    message_not_found: 'errors.messageNotFound',
    conversation_busy: 'errors.conversationBusy',
    generation_failed: 'errors.generationFailed',
    quota_exceeded: 'errors.quotaExceeded',
    insufficient_credits: 'errors.insufficientCredits',
    expert_limit_reached: 'errors.expertLimitReached',
    storage_quota_exceeded: 'errors.storageQuotaExceeded',
    billing_gateway_unavailable: 'errors.billingGatewayUnavailable',
    billing_gateway_error: 'errors.billingGatewayError',
    invalid_purchase: 'errors.invalidPurchase',
    purchase_not_found: 'errors.purchaseNotFound',
    purchase_already_completed: 'errors.purchaseAlreadyCompleted',
    payment_verification_failed: 'errors.paymentVerificationFailed',
    payment_amount_mismatch: 'errors.paymentAmountMismatch',
    payment_currency_mismatch: 'errors.paymentCurrencyMismatch',
    credit_pack_unavailable: 'errors.creditPackUnavailable',
    plan_unavailable: 'errors.planUnavailable',
    system_workspace_checkout_forbidden: 'errors.systemWorkspaceCheckoutForbidden',
    app_not_found: 'errors.appNotFound',
    app_not_available: 'errors.appNotAvailable',
    app_already_installed: 'errors.appAlreadyInstalled',
    app_not_installed: 'errors.appNotInstalled',
    app_billing_required: 'errors.appBillingRequired',
    app_install_forbidden: 'errors.appInstallForbidden',
    app_installation_not_found: 'errors.appInstallationNotFound',
    app_plan_not_found: 'errors.appPlanNotFound',
    app_plan_inactive: 'errors.appPlanInactive',
    app_plan_mismatch: 'errors.appPlanMismatch',
    app_already_licensed: 'errors.appAlreadyLicensed',
    app_subscription_required: 'errors.appSubscriptionRequired',
    app_subscription_expired: 'errors.appSubscriptionExpired',
    app_subscription_already_active: 'errors.appSubscriptionAlreadyActive',
    app_renewal_not_allowed: 'errors.appRenewalNotAllowed',
    app_currency_not_supported: 'errors.appCurrencyNotSupported',
    app_checkout_forbidden: 'errors.appCheckoutForbidden',
    app_checkout_in_progress: 'errors.appCheckoutInProgress',
    app_purchase_not_payable: 'errors.appPurchaseNotPayable',
    connector_not_available: 'errors.connectorNotAvailable',
    connector_not_supported: 'errors.connectorNotSupported',
    connector_limit_reached: 'errors.connectorLimitReached',
    connector_not_found: 'errors.connectorNotFound',
    connector_already_disconnected: 'errors.connectorAlreadyDisconnected',
    connector_credentials_invalid: 'errors.connectorCredentialsInvalid',
    connector_credentials_expired: 'errors.connectorCredentialsExpired',
    connector_connection_failed: 'errors.connectorConnectionFailed',
    connector_health_check_failed: 'errors.connectorHealthCheckFailed',
    connector_sync_not_supported: 'errors.connectorSyncNotSupported',
    connector_sync_in_progress: 'errors.connectorSyncInProgress',
    connector_sync_not_found: 'errors.connectorSyncNotFound',
    google_drive_not_configured: 'errors.googleDriveNotConfigured',
    google_drive_authorization_failed: 'errors.googleDriveAuthorizationFailed',
    google_drive_reauthorization_required: 'errors.googleDriveReauthorizationRequired',
    google_drive_file_not_found: 'errors.googleDriveFileNotFound',
    google_drive_file_access_denied: 'errors.googleDriveFileAccessDenied',
    google_drive_file_type_unsupported: 'errors.googleDriveFileTypeUnsupported',
    google_drive_export_too_large: 'errors.googleDriveExportTooLarge',
    google_drive_download_failed: 'errors.googleDriveDownloadFailed',
    google_drive_rate_limited: 'errors.googleDriveRateLimited',
    google_drive_watch_failed: 'errors.googleDriveWatchFailed',
    google_drive_sync_failed: 'errors.googleDriveSyncFailed',
    microsoft_onedrive_not_configured: 'errors.microsoftOneDriveNotConfigured',
    microsoft_onedrive_authorization_failed:
      'errors.microsoftOneDriveAuthorizationFailed',
    microsoft_onedrive_reauthorization_required:
      'errors.microsoftOneDriveReauthorizationRequired',
    microsoft_onedrive_drive_not_supported:
      'errors.microsoftOneDriveDriveNotSupported',
    microsoft_onedrive_item_not_found: 'errors.microsoftOneDriveItemNotFound',
    microsoft_onedrive_access_denied: 'errors.microsoftOneDriveAccessDenied',
    microsoft_onedrive_file_type_unsupported:
      'errors.microsoftOneDriveFileTypeUnsupported',
    microsoft_onedrive_conversion_failed:
      'errors.microsoftOneDriveConversionFailed',
    microsoft_onedrive_download_failed: 'errors.microsoftOneDriveDownloadFailed',
    microsoft_onedrive_rate_limited: 'errors.microsoftOneDriveRateLimited',
    microsoft_onedrive_delta_resync_required:
      'errors.microsoftOneDriveDeltaResyncRequired',
    microsoft_onedrive_subscription_failed:
      'errors.microsoftOneDriveSubscriptionFailed',
    microsoft_onedrive_sync_failed: 'errors.microsoftOneDriveSyncFailed',
    openwa_not_configured: 'errors.openwaNotConfigured',
    openwa_unavailable: 'errors.openwaUnavailable',
    openwa_unauthorized: 'errors.openwaUnauthorized',
    openwa_timeout: 'errors.openwaTimeout',
    openwa_request_invalid: 'errors.openwaRequestInvalid',
    openwa_session_not_found: 'errors.openwaSessionNotFound',
    openwa_session_conflict: 'errors.openwaSessionConflict',
    openwa_qr_not_ready: 'errors.openwaQrNotReady',
    openwa_pairing_failed: 'errors.openwaPairingFailed',
    openwa_phone_invalid: 'errors.openwaPhoneInvalid',
    openwa_webhook_failed: 'errors.openwaWebhookFailed',
    openwa_send_failed: 'errors.openwaSendFailed',
    channel_binding_required: 'errors.channelBindingRequired',
    channel_expert_invalid: 'errors.channelExpertInvalid',
    invitation_not_found: 'members.errors.notFound',
    invitation_already_exists: 'members.errors.alreadyInvited',
    already_workspace_member: 'members.errors.alreadyMember',
    invalid_invitation: 'invitations.invalid',
    invitation_expired: 'invitations.expired',
    invitation_revoked: 'invitations.revoked',
    invitation_email_mismatch: 'invitations.emailMismatch',
    invitation_already_accepted: 'invitations.alreadyAccepted',
    email_delivery_failed: 'members.errors.emailFailed',
  };
  return map[code as ApiErrorCode] ?? 'errors.generic';
}

/** Detect ORM / SQL / stack dumps that must never be shown to end users. */
const TECHNICAL_ERROR_RE =
  /\b(psycopg|sqlalchemy|asyncpg|celery|traceback|CheckViolation|IntegrityError|OperationalError|ProgrammingError|DataError)\b|violates check constraint|\bSQL:\s*(INSERT|UPDATE|SELECT|DELETE|WITH)\b|File "[^"]+\.py"|site-packages|DETAIL:\s*Failing row|\[SQL:\s|Background on this error at:/i;

export function looksTechnicalError(message: string | null | undefined): boolean {
  const text = (message ?? '').trim();
  if (!text) return false;
  if (text.length > 280) return true;
  return TECHNICAL_ERROR_RE.test(text);
}

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

/**
 * User-facing error copy. Prefer mapped error codes; never surface technical dumps.
 */
export function friendlyDisplayError(
  t: TranslateFn,
  opts: { code?: string | null; message?: string | null } = {},
): string {
  const code = (opts.code ?? '').trim();
  if (code) {
    const key = errorMessageKey(code);
    if (key !== 'errors.generic') {
      return t(key);
    }
  }

  const message = (opts.message ?? '').trim();
  if (message && !looksTechnicalError(message)) {
    return message;
  }

  return t('errors.generic');
}

export function isQuotaErrorCode(code: string | null | undefined): boolean {
  return (
    code === 'quota_exceeded' ||
    code === 'insufficient_credits' ||
    code === 'expert_limit_reached' ||
    code === 'storage_quota_exceeded' ||
    code === 'connector_limit_reached'
  );
}
