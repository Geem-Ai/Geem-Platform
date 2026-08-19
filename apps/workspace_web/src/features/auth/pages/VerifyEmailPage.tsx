import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { BadgeCheck, LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { continueAfterAuth } from '@/app/router/guards';
import { isInvitationAcceptPath } from '@/features/members/lib/invitation-path';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import { AuthFormHeader } from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { useAuth } from '@/features/auth/AuthProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const { status, completeEmailVerification } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const token = useMemo(() => (searchParams.get('token') || '').trim(), [searchParams]);
  const from = (location.state as { from?: string } | null)?.from;
  const started = useRef(false);
  const [errorKey, setErrorKey] = useState<string | null>(
    token ? null : 'errors.invalidVerificationToken',
  );
  const [verifying, setVerifying] = useState(Boolean(token));

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    void (async () => {
      setVerifying(true);
      try {
        const me = await completeEmailVerification(token);
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
        setVerifying(false);
      }
    })();
  }, [completeEmailVerification, from, navigate, token]);

  if (status === 'authenticated' && !errorKey) {
    return <Navigate to={continueAfterAuth(from)} replace />;
  }

  return (
    <AuthLayout>
      <DocumentTitle title={t('auth.verifyEmailTitle')} />
      <AuthFormHeader
        icon={BadgeCheck}
        title={t('auth.verifyEmailTitle')}
        subtitle={
          verifying ? t('auth.verifyEmailWorking') : t('auth.verifyEmailSubtitle')
        }
      />
      <div className="space-y-5" data-testid="verify-email-panel">
        {verifying && !errorKey && (
          <div
            className="flex justify-center rounded-2xl border border-primary/15 bg-primary/5 px-5 py-8"
            data-testid="verify-email-loading"
          >
            <LoaderCircle
              className="size-7 animate-spin text-primary drop-shadow-sm"
              aria-hidden
            />
            <span className="sr-only">{t('auth.verifyEmailWorking')}</span>
          </div>
        )}
        {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
        {errorKey && (
          <p className="text-center text-sm text-muted-foreground">
            <Link
              to="/check-email"
              className="font-medium text-primary hover:underline"
            >
              {t('auth.checkEmailResend')}
            </Link>
            {' · '}
            <Link to="/login" className="font-medium text-primary hover:underline">
              {t('auth.backToSignIn')}
            </Link>
          </p>
        )}
      </div>
    </AuthLayout>
  );
}
