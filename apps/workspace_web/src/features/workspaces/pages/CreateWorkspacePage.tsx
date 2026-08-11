import { useEffect, useState, type FormEvent } from 'react';
import { Helmet } from 'react-helmet-async';
import { Navigate, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/features/auth/AuthProvider';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { suggestSlugFromName } from '@/features/workspaces/lib/hostname';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ApiError, errorMessageKey } from '@/services/api/errors';

/** Create workspace for users who already have memberships (switcher action). */
export function CreateWorkspacePage() {
  const { t } = useTranslation();
  const { status } = useAuth();
  const { createWorkspace } = useWorkspace();
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
          {t('shell.createWorkspace')} · {t('app.name')}
        </title>
      </Helmet>
      <Card>
        <CardHeader>
          <CardTitle>{t('shell.createWorkspace')}</CardTitle>
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
              <label htmlFor="new-ws-name" className="text-sm font-medium">
                {t('onboarding.workspaceName')}
              </label>
              <Input
                id="new-ws-name"
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="new-ws-slug" className="text-sm font-medium">
                {t('onboarding.workspaceSlug')}
              </label>
              <Input
                id="new-ws-slug"
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
          <CardFooter className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => navigate(-1)}
              disabled={submitting}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              className="flex-1"
              disabled={submitting || !name.trim() || !slug.trim()}
            >
              {submitting ? t('onboarding.creating') : t('onboarding.create')}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </AuthLayout>
  );
}
