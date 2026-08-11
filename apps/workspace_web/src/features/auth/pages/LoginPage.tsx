import { useState, type FormEvent } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { useAuth } from '@/features/auth/AuthProvider';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function LoginPage() {
  const { t } = useTranslation();
  const { status, login, sessionExpired, clearSessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(
    sessionExpired ? 'errors.sessionExpired' : null,
  );
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated') {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    clearSessionExpired();
    try {
      const me = await login(email.trim(), password);
      const from = (location.state as { from?: string } | null)?.from;
      if (me.workspaces.length === 0) {
        navigate('/onboarding', { replace: true });
      } else {
        navigate(from && from !== '/login' ? from : '/', { replace: true });
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
      <Helmet>
        <title>
          {t('auth.loginTitle')} · {t('app.name')}
        </title>
      </Helmet>
      <Card>
        <CardHeader>
          <CardTitle>{t('auth.loginTitle')}</CardTitle>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            {errorKey && (
              <p className="text-sm text-destructive" role="alert">
                {t(errorKey)}
              </p>
            )}
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium">
                {t('auth.email')}
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium">
                {t('auth.password')}
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                minLength={1}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? t('auth.signingIn') : t('auth.signIn')}
            </Button>
            <p className="text-sm text-muted-foreground text-center">
              {t('auth.noAccount')}{' '}
              <Link to="/register" className="text-primary hover:underline">
                {t('auth.registerLink')}
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </AuthLayout>
  );
}
