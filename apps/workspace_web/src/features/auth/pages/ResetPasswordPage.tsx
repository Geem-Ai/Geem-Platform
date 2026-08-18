import { useMemo, useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { continueAfterAuth } from '@/app/router/guards';
import { isInvitationAcceptPath } from '@/features/members/lib/invitation-path';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import {
  AuthFormHeader,
  AuthPasswordField,
} from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { useAuth } from '@/features/auth/AuthProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const { status, completePasswordReset } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const token = useMemo(() => (searchParams.get('token') || '').trim(), [searchParams]);

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(
    token ? null : 'errors.invalidResetToken',
  );
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from;

  if (status === 'authenticated') {
    return <Navigate to={continueAfterAuth(from)} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) {
      setErrorKey('errors.invalidResetToken');
      return;
    }
    if (password !== confirm) {
      setErrorKey('errors.passwordMismatch');
      return;
    }
    setSubmitting(true);
    setErrorKey(null);
    try {
      const me = await completePasswordReset(token, password);
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
      <DocumentTitle title={t('auth.resetTitle')} />
      <AuthFormHeader
        title={t('auth.resetTitle')}
        subtitle={t('auth.resetSubtitle')}
      />
      <form
        onSubmit={onSubmit}
        className="space-y-5"
        data-testid="reset-password-form"
        aria-busy={submitting}
      >
        {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
        <AuthPasswordField
          id="password"
          value={password}
          onChange={setPassword}
          disabled={submitting || !token}
          autoComplete="new-password"
          minLength={8}
          maxLength={128}
          hint={t('auth.passwordHint')}
          autoFocus={Boolean(token)}
        />
        <AuthPasswordField
          id="confirm-password"
          name="confirm-password"
          label={t('auth.confirmPassword')}
          value={confirm}
          onChange={setConfirm}
          disabled={submitting || !token}
          autoComplete="new-password"
          minLength={8}
          maxLength={128}
          placeholder={t('auth.confirmPasswordPlaceholder')}
        />
        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={submitting || !token}
        >
          {submitting ? (
            <LoaderCircle className="animate-spin" aria-hidden />
          ) : null}
          {submitting ? t('auth.resetSubmitting') : t('auth.resetSubmit')}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          <Link to="/forgot-password" className="font-medium text-primary hover:underline">
            {t('auth.forgotLink')}
          </Link>
          {' · '}
          <Link to="/login" className="font-medium text-primary hover:underline">
            {t('auth.backToSignIn')}
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
