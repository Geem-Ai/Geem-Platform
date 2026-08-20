import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LoaderCircle, LogIn } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import {
  AuthEmailField,
  AuthFormHeader,
  AuthPasswordField,
} from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import {
  PlatformAccessDeniedError,
  useAuth,
} from '@/features/auth/AuthProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function LoginPage() {
  const { t } = useTranslation();
  const { status, login, sessionExpired, clearSessionExpired, accessDenied, clearAccessDenied } =
    useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from;

  if (status === 'authenticated') {
    return <Navigate to={from && from.startsWith('/') && !from.startsWith('//') ? from : '/'} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    clearSessionExpired();
    clearAccessDenied();
    try {
      await login(email.trim(), password);
      const dest =
        from && from.startsWith('/') && !from.startsWith('//') && from !== '/login'
          ? from
          : '/';
      navigate(dest, { replace: true });
    } catch (err) {
      if (err instanceof PlatformAccessDeniedError) {
        return;
      }
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
        icon={LogIn}
        title={t('auth.loginTitle')}
        subtitle={t('auth.loginSubtitle')}
      />
      <form
        onSubmit={onSubmit}
        className="space-y-5"
        data-testid="login-form"
        aria-busy={submitting}
      >
        {accessDenied && !errorKey && (
          <AuthAlert>
            <span data-testid="platform-access-required">
              {t('auth.accessRequiredTitle')}. {t('auth.accessRequiredBody')}
            </span>
          </AuthAlert>
        )}
        {sessionExpired && !errorKey && !accessDenied && (
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
        />
        <Button
          type="submit"
          size="lg"
          className="auth-submit-button w-full"
          disabled={submitting}
          data-testid="login-submit"
        >
          {submitting ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
          {submitting ? t('auth.signingIn') : t('auth.signIn')}
        </Button>
      </form>
    </AuthLayout>
  );
}
