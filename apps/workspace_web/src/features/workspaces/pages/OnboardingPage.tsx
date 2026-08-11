import { useEffect, useState, type FormEvent } from 'react';
import { Helmet } from 'react-helmet-async';
import { Navigate, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/features/auth/AuthProvider';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { suggestSlugFromName } from '@/features/workspaces/lib/hostname';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function OnboardingPage() {
  const { t } = useTranslation();
  const { status } = useAuth();
  const { availableWorkspaces, createWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!slugTouched) {
      setSlug(suggestSlugFromName(name));
    }
  }, [name, slugTouched]);

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />;
  }

  if (availableWorkspaces.length > 0) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    try {
      await createWorkspace({ name: name.trim(), slug: slug.trim() });
      navigate('/', { replace: true });
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
          {t('onboarding.title')} · {t('app.name')}
        </title>
      </Helmet>
      <Card>
        <CardHeader>
          <CardTitle>{t('onboarding.title')}</CardTitle>
          <CardDescription>{t('onboarding.description')}</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            {errorKey && (
              <p className="text-sm text-destructive" role="alert">
                {t(errorKey)}
              </p>
            )}
            <div className="space-y-2">
              <label htmlFor="ws-name" className="text-sm font-medium">
                {t('onboarding.workspaceName')}
              </label>
              <Input
                id="ws-name"
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="ws-slug" className="text-sm font-medium">
                {t('onboarding.workspaceSlug')}
              </label>
              <Input
                id="ws-slug"
                required
                minLength={3}
                maxLength={63}
                value={slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setSlug(e.target.value.toLowerCase());
                }}
                disabled={submitting}
              />
              <p className="text-xs text-muted-foreground">{t('onboarding.slugHint')}</p>
            </div>
          </CardContent>
          <CardFooter>
            <Button type="submit" className="w-full" disabled={submitting || !name.trim() || !slug.trim()}>
              {submitting ? t('onboarding.creating') : t('onboarding.create')}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </AuthLayout>
  );
}
