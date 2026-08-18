import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { continueAfterAuth } from '@/app/router/guards';
import { isInvitationAcceptPath } from '@/features/members/lib/invitation-path';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import {
  AuthEmailField,
  AuthFormHeader,
  AuthPasswordField,
} from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { useAuth } from '@/features/auth/AuthProvider';
import { Button } from '@/components/ui/button';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function RegisterPage() {
  const { t } = useTranslation();
  const { status, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated') {
    return <Navigate to={continueAfterAuth(from)} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    try {
      const me = await register(email.trim(), password);
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
      <DocumentTitle title={t('auth.registerTitle')} />
      <AuthFormHeader
        title={t('auth.registerTitle')}
        subtitle={t('auth.registerSubtitle')}
      />
      <form
        onSubmit={onSubmit}
        className="space-y-5"
        data-testid="register-form"
        aria-busy={submitting}
      >
        {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
        <AuthEmailField
          id="reg-email"
          value={email}
          onChange={setEmail}
          disabled={submitting}
          autoFocus
        />
        <AuthPasswordField
          id="reg-password"
          value={password}
          onChange={setPassword}
          disabled={submitting}
          autoComplete="new-password"
          minLength={8}
          maxLength={128}
          hint={
            <p className="text-xs text-muted-foreground">{t('auth.passwordHint')}</p>
          }
        />
        <Button type="submit" size="lg" className="w-full" disabled={submitting}>
          {submitting ? (
            <LoaderCircle className="animate-spin" aria-hidden />
          ) : null}
          {submitting ? t('auth.creatingAccount') : t('auth.createAccount')}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          {t('auth.hasAccount')}{' '}
          <Link
            to="/login"
            state={from ? { from } : undefined}
            className="font-medium text-primary hover:underline"
          >
            {t('auth.loginLink')}
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
