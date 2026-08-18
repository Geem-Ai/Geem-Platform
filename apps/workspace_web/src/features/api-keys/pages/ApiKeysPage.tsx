import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BookOpen, KeyRound, Plus, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { usePermissions } from '@/features/authz/usePermissions';
import { WorkspacePermission } from '@/features/authz/permissions';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { ApiKey, CreatedApiKey } from '@/services/api/api-keys';
import { ApiKeysList } from '../components/ApiKeysList';
import { ApiQuickStart } from '../components/ApiQuickStart';
import { CreateApiKeyDialog } from '../components/CreateApiKeyDialog';
import { CreatedSecretDialog } from '../components/CreatedSecretDialog';
import { RevokeApiKeyDialog } from '../components/RevokeApiKeyDialog';
import { useApiKeys, useRevokeApiKey } from '../hooks/useApiKeyQueries';

function KeysSkeleton() {
  return (
    <div className="space-y-3 p-5" data-testid="api-keys-loading">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-10 rounded bg-muted animate-pulse" />
      ))}
    </div>
  );
}

export function ApiKeysPage() {
  const { t } = useTranslation();
  const { workspaceId, can } = usePermissions();
  const canView = can(WorkspacePermission.API_KEYS_VIEW);
  const canCreate = can(WorkspacePermission.API_KEYS_CREATE);
  const canRevoke = can(WorkspacePermission.API_KEYS_REVOKE);
  const keysQuery = useApiKeys({ enabled: canView });
  const revoke = useRevokeApiKey();

  const [createOpen, setCreateOpen] = useState(false);
  const [quickStartOpen, setQuickStartOpen] = useState(false);
  const [plaintext, setPlaintext] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);

  useEffect(() => {
    setPlaintext(null);
    setCreateOpen(false);
    setQuickStartOpen(false);
    setRevokeTarget(null);
  }, [workspaceId]);

  function handleCreated(created: CreatedApiKey) {
    setPlaintext(created.key);
  }

  function handleRevoke() {
    if (!revokeTarget) return;
    revoke.mutate(revokeTarget.id, {
      onSuccess: () => {
        toast.success(t('apiKeys.revoked'));
        setRevokeTarget(null);
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) {
          toast.error(t(errorMessageKey(err.code)));
        } else {
          toast.error(t('errors.generic'));
        }
      },
    });
  }

  const keys = keysQuery.data ?? [];
  const forbidden =
    !canView ||
    (keysQuery.isError &&
      keysQuery.error instanceof ApiError &&
      (keysQuery.error.code === 'forbidden' ||
        keysQuery.error.code === 'insufficient_workspace_role'));

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('apiKeys.title')} />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {t('apiKeys.eyebrow')}
          </p>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
            {t('apiKeys.title')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            {t('apiKeys.description')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setQuickStartOpen(true)}
            data-testid="open-api-quick-start"
          >
            <BookOpen className="size-3.5" />
            {t('apiKeys.quickStartTitle')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void keysQuery.refetch()}
            disabled={keysQuery.isFetching}
          >
            <RefreshCw className={keysQuery.isFetching ? 'size-3.5 animate-spin' : 'size-3.5'} />
            {t('apiKeys.refresh')}
          </Button>
          {canCreate ? (
            <Button
              type="button"
              size="sm"
              onClick={() => setCreateOpen(true)}
              data-testid="create-api-key"
            >
              <Plus className="size-3.5" />
              {t('apiKeys.create')}
            </Button>
          ) : null}
        </div>
      </div>

      <Card className="shadow-xs">
        <CardHeader>
          <CardTitle>{t('apiKeys.listTitle')}</CardTitle>
          <CardDescription>{t('apiKeys.listHint')}</CardDescription>
        </CardHeader>
        <CardContent>
          {keysQuery.isLoading ? <KeysSkeleton /> : null}

          {!canView || forbidden ? (
            <div className="py-10 text-center space-y-2" data-testid="api-keys-forbidden">
              <KeyRound className="size-8 mx-auto text-muted-foreground" aria-hidden />
              <p className="text-sm text-muted-foreground">{t('apiKeys.memberHint')}</p>
            </div>
          ) : null}

          {canView && keysQuery.isError && !forbidden ? (
            <div className="py-10 text-center space-y-3" data-testid="api-keys-error">
              <p className="text-sm text-destructive">{t('apiKeys.loadError')}</p>
              <Button type="button" onClick={() => void keysQuery.refetch()}>
                {t('apiKeys.retry')}
              </Button>
            </div>
          ) : null}

          {canView && !keysQuery.isLoading && !keysQuery.isError && keys.length === 0 ? (
            <div className="py-12 text-center space-y-3" data-testid="api-keys-empty">
              <KeyRound className="size-8 mx-auto text-muted-foreground" aria-hidden />
              <p className="font-medium">{t('apiKeys.emptyTitle')}</p>
              <p className="text-sm text-muted-foreground">{t('apiKeys.emptyHint')}</p>
              {canCreate ? (
              <Button type="button" onClick={() => setCreateOpen(true)}>
                <Plus className="size-3.5" />
                {t('apiKeys.create')}
              </Button>
              ) : null}
            </div>
          ) : null}

          {canView && !keysQuery.isLoading && !keysQuery.isError && keys.length > 0 ? (
            <ApiKeysList keys={keys} canManage={canRevoke} onRevoke={setRevokeTarget} />
          ) : null}
        </CardContent>
      </Card>

      <ApiQuickStart open={quickStartOpen} onOpenChange={setQuickStartOpen} />

      {canCreate ? (
        <CreateApiKeyDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={handleCreated}
        />
      ) : null}
      <CreatedSecretDialog secret={plaintext} onClose={() => setPlaintext(null)} />
      <RevokeApiKeyDialog
        apiKey={revokeTarget}
        open={Boolean(revokeTarget)}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null);
        }}
        onConfirm={handleRevoke}
        isPending={revoke.isPending}
      />
    </div>
  );
}
