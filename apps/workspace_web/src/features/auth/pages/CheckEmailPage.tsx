import { useMemo, useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { LoaderCircle, MailCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { continueAfterAuth } from '@/app/router/guards';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import {
  AuthEmailField,
  AuthFormHeader,
} from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { useAuth } from '@/features/auth/AuthProvider';
import { resendVerification } from '@/services/api';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function CheckEmailPage() {
  const { t } = useTranslation();
  const { status } = useAuth();
  const location = useLocation();
  const state = location.state as { email?: string; from?: string } | null;
  const initialEmail = (state?.email || '').trim();
  const from = state?.from;

  const [email, setEmail] = useState(initialEmail);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [resent, setResent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const subtitle = useMemo(
    () =>
      initialEmail
        ? t('auth.checkEmailSubtitleKnown', { email: initialEmail })
        : t('auth.checkEmailSubtitle'),
    [initialEmail, t],
  );

  if (status === 'authenticated') {
    return <Navigate to={continueAfterAuth(from)} replace />;
  }

  const onResend = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) {
      setErrorKey('errors.validation');
      return;
    }
    setSubmitting(true);
    setErrorKey(null);
    setResent(false);
    try {
      await resendVerification(trimmed);
      setResent(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorKey(errorMessageKey(err.code));
      } else {
        setErrorKey('errors.generic');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <DocumentTitle title={t('auth.checkEmailTitle')} />
      <AuthFormHeader
        icon={MailCheck}
        title={t('auth.checkEmailTitle')}
        subtitle={subtitle}
      />
      <form
        onSubmit={onResend}
        className="space-y-5"
        data-testid="check-email-form"
        aria-busy={submitting}
      >
        {resent && (
          <AuthAlert tone="success">{t('auth.checkEmailResent')}</AuthAlert>
        )}
        {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
        {!initialEmail && (
          <AuthEmailField
            id="verify-email"
            value={email}
            onChange={setEmail}
            disabled={submitting}
            autoFocus
          />
        )}
        <Button
          type="submit"
          size="lg"
          className="auth-submit-button w-full"
          disabled={submitting}
        >
          {submitting ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
          ) : null}
          {submitting ? t('auth.checkEmailResending') : t('auth.checkEmailResend')}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          <Link
            to="/login"
            state={from ? { from } : undefined}
            className="font-medium text-primary hover:underline"
          >
            {t('auth.backToSignIn')}
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
