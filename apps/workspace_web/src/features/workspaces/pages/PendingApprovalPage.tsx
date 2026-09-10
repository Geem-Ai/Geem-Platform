import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Clock3, LoaderCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { continueAfterAuth } from '@/app/router/guards';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/features/auth/AuthProvider';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import { AuthFormHeader } from '@/features/auth/components/AuthFields';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import {
  hasActiveWorkspace,
  isPendingWorkspace,
} from '@/features/workspaces/lib/workspace-status';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';

export function PendingApprovalPage() {
  const { t } = useTranslation();
  const { status, me, reloadMe } = useAuth();
  const { refreshWorkspaces } = useWorkspace();
  const navigate = useNavigate();
  const [refreshing, setRefreshing] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />;
  }

  const workspaces = me?.workspaces ?? [];
  if (workspaces.length === 0) {
    return <Navigate to="/onboarding" replace />;
  }
  if (hasActiveWorkspace(workspaces)) {
    return <Navigate to={continueAfterAuth(null)} replace />;
  }

  const pending = workspaces.filter(isPendingWorkspace);
  const primary = pending[0] ?? workspaces[0];

  const onRefresh = async () => {
    setRefreshing(true);
    setErrorKey(null);
    try {
      const data = await reloadMe();
      await refreshWorkspaces();
      if (hasActiveWorkspace(data.workspaces)) {
        navigate(continueAfterAuth(null), { replace: true });
      }
    } catch {
      setErrorKey('errors.generic');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <AuthLayout>
      <DocumentTitle title={t('pendingApproval.title')} />
      <AuthFormHeader
        icon={Clock3}
        title={t('pendingApproval.title')}
        subtitle={
          primary
            ? t('pendingApproval.subtitleNamed', { name: primary.name })
            : t('pendingApproval.subtitle')
        }
      />
      <div className="space-y-5" data-testid="pending-approval">
        {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
        <p className="text-sm text-muted-foreground">
          {t('pendingApproval.body')}
        </p>
        <Button
          type="button"
          size="lg"
          className="auth-submit-button w-full"
          disabled={refreshing}
          onClick={() => void onRefresh()}
          data-testid="pending-approval-refresh"
        >
          {refreshing ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
          ) : (
            <RefreshCw className="size-4" aria-hidden />
          )}
          {refreshing
            ? t('pendingApproval.refreshing')
            : t('pendingApproval.refresh')}
        </Button>
      </div>
    </AuthLayout>
  );
}
