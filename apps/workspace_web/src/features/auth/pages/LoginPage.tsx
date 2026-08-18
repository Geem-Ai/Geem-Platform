import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { continueAfterAuth } from '@/app/router/guards';
import { isInvitationAcceptPath } from '@/features/members/lib/invitation-path';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import {
  AuthEmailField,
  AuthFormHeader,
  AuthPasswordField,
} from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { useAuth } from '@/features/auth/AuthProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function LoginPage() {
  const { t } = useTranslation();
  const { status, login, sessionExpired, clearSessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from;

  if (status === 'authenticated') {
    return <Navigate to={continueAfterAuth(from)} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    clearSessionExpired();
    try {
      const me = await login(email.trim(), password);
      const dest = continueAfterAuth(from);
      if (isInvitationAcceptPath(dest) || me.workspaces.length > 0) {
        navigate(dest, { replace: true });
      } else {
        navigate('/onboarding', { replace: true, state: { from } });
      }
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
      <DocumentTitle title={t('auth.loginTitle')} />
      <AuthFormHeader
        title={t('auth.loginTitle')}
        subtitle={t('auth.loginSubtitle')}
      />
      <form
        onSubmit={onSubmit}
        className="space-y-5"
        data-testid="login-form"
        aria-busy={submitting}
      >
        {sessionExpired && !errorKey && (
          <AuthAlert tone="warning">{t('errors.sessionExpired')}</AuthAlert>
        )}
        {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
        <AuthEmailField
          id="email"
          value={email}
          onChange={setEmail}
          disabled={submitting}
          autoFocus
        />
        <AuthPasswordField
          id="password"
          value={password}
          onChange={setPassword}
          disabled={submitting}
          autoComplete="current-password"
          minLength={1}
        />
        <p className="text-end text-sm">
          <Link
            to="/forgot-password"
            className="font-medium text-primary hover:underline"
            data-testid="forgot-password-link"
          >
            {t('auth.forgotLink')}
          </Link>
        </p>
        <Button type="submit" size="lg" className="w-full" disabled={submitting}>
          {submitting ? (
            <LoaderCircle className="animate-spin" aria-hidden />
          ) : null}
          {submitting ? t('auth.signingIn') : t('auth.signIn')}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          {t('auth.noAccount')}{' '}
          <Link
            to="/register"
            state={from ? { from } : undefined}
            className="font-medium text-primary hover:underline"
          >
            {t('auth.registerLink')}
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
