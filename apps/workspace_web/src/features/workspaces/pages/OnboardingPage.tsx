import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { continueAfterAuth } from '@/app/router/guards';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/features/auth/AuthProvider';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import { AuthFormHeader } from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { suggestSlugFromName } from '@/features/workspaces/lib/hostname';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { WorkspaceSlugInput } from '@/features/workspaces/components/WorkspaceSlugInput';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function OnboardingPage() {
  const { t } = useTranslation();
  const { status } = useAuth();
  const { availableWorkspaces, createWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
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
    return <Navigate to={continueAfterAuth(from)} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    try {
      await createWorkspace({ name: name.trim(), slug: slug.trim() });
      navigate(continueAfterAuth(from), { replace: true });
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
      <DocumentTitle title={t('onboarding.title')} />
      <AuthFormHeader
        title={t('onboarding.title')}
        subtitle={t('onboarding.description')}
      />
      <form onSubmit={onSubmit} className="space-y-5" aria-busy={submitting}>
        {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
        <div className="space-y-2">
          <Label htmlFor="ws-name">{t('onboarding.workspaceName')}</Label>
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
          <Label htmlFor="ws-slug">{t('onboarding.workspaceSlug')}</Label>
          <WorkspaceSlugInput
            id="ws-slug"
            value={slug}
            onChange={(next) => {
              setSlugTouched(true);
              setSlug(next);
            }}
            disabled={submitting}
          />
          <p className="text-xs text-muted-foreground">{t('onboarding.slugHint')}</p>
        </div>
        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={submitting || !name.trim() || !slug.trim()}
        >
          {submitting ? <LoaderCircle className="animate-spin" aria-hidden /> : null}
          {submitting ? t('onboarding.creating') : t('onboarding.create')}
        </Button>
      </form>
    </AuthLayout>
  );
}
