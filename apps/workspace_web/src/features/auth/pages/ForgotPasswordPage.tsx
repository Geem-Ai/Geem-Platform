import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { KeyRound, LoaderCircle } from 'lucide-react';
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
import { forgotPassword } from '@/services/api';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const { status } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from;

  if (status === 'authenticated') {
    return <Navigate to={continueAfterAuth(from)} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    try {
      await forgotPassword(email.trim());
      setSubmitted(true);
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
      <DocumentTitle title={t('auth.forgotTitle')} />
      <AuthFormHeader
        icon={KeyRound}
        title={t('auth.forgotTitle')}
        subtitle={
          submitted ? t('auth.forgotSuccessSubtitle') : t('auth.forgotSubtitle')
        }
      />
      {submitted ? (
        <div
          className="space-y-5 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5"
          data-testid="forgot-password-success"
        >
          <AuthAlert tone="success">{t('auth.forgotSuccessBody')}</AuthAlert>
          <p className="text-center text-sm text-muted-foreground">
            <Link
              to="/login"
              state={from ? { from } : undefined}
              className="font-medium text-primary hover:underline"
            >
              {t('auth.backToSignIn')}
            </Link>
          </p>
        </div>
      ) : (
        <form
          onSubmit={onSubmit}
          className="space-y-5"
          data-testid="forgot-password-form"
          aria-busy={submitting}
        >
          {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
          <AuthEmailField
            id="email"
            value={email}
            onChange={setEmail}
            disabled={submitting}
            autoFocus
          />
          <Button
            type="submit"
            size="lg"
            className="auth-submit-button w-full"
            disabled={submitting}
          >
            {submitting ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : null}
            {submitting ? t('auth.forgotSubmitting') : t('auth.forgotSubmit')}
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
      )}
    </AuthLayout>
  );
}
