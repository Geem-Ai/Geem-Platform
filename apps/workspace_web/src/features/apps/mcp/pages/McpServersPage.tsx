import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Plus, RefreshCw, Server, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { WorkspacePermission } from '@/features/authz/permissions';
import { usePermissions } from '@/features/authz/usePermissions';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { McpServer } from '@/services/api/mcp';
import { DeleteMcpServerDialog } from '../components/DeleteMcpServerDialog';
import { McpServerDialog } from '../components/McpServerDialog';
import { McpUsageSummary } from '../components/McpUsageSummary';
import {
  useDeleteMcpServer,
  useMcpServers,
  useReauthorizeMcpServer,
} from '../hooks/useMcpQueries';
import { displayedServerStatus } from './mcpServerStatus';

function serverName(server: McpServer): string {
  return server.display_name || server.endpoint_host || server.id;
}

function statusVariant(status: string) {
  if (status === 'healthy' || status === 'active' || status === 'connected') return 'success' as const;
  if (status === 'error' || status === 'failed' || status === 'unhealthy' || status === 'reauthorization_required') return 'destructive' as const;
  return 'secondary' as const;
}

export function McpServersPage() {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const [searchParams] = useSearchParams();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [serverToDelete, setServerToDelete] = useState<McpServer | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const query = useMcpServers({ limit: 100, offset: 0 });
  const remove = useDeleteMcpServer();
  const reauthorize = useReauthorizeMcpServer();
  const canConnect = can(WorkspacePermission.APPS_CONNECT);
  const canApproveExternal = can(WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL);
  const oauthResult = searchParams.get('oauth') || searchParams.get('status');
  const items = query.data?.items ?? [];

  async function removeServer(server: McpServer) {
    try {
      await remove.mutateAsync(server.id);
      setServerToDelete(null);
      setDeleteError(null);
      toast.success(t('apps.mcp.serverDeleted'));
    } catch (error) {
      const message = t(
        errorMessageKey(error instanceof ApiError ? error.code : 'unknown'),
      );
      setDeleteError(message);
      toast.error(message);
    }
  }

  async function startReauthorization(server: McpServer) {
    try {
      const result = await reauthorize.mutateAsync({
        connectionId: server.id,
        returnPath: '/apps/mcp',
      });
      if (result.authorization_url) window.location.assign(result.authorization_url);
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-6 ms-auto me-auto" data-testid="mcp-servers-page">
      <DocumentTitle title={t('apps.mcp.title')} />

      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ms-2 mb-1">
            <Link to="/apps/mcp-connectors">
              <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
              {t('apps.backToStore')}
            </Link>
          </Button>
          <h1 className="text-2xl font-semibold tracking-tight">{t('apps.mcp.title')}</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">{t('apps.mcp.description')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canApproveExternal ? (
            <Button asChild variant="outline" size="sm">
              <Link to="/apps/mcp/external-approvals">{t('apps.mcp.externalApprovals.title')}</Link>
            </Button>
          ) : null}
          {canConnect ? (
            <Button type="button" size="sm" onClick={() => setDialogOpen(true)}>
              <Plus className="size-4" aria-hidden />
              {t('apps.mcp.addServer')}
            </Button>
          ) : null}
        </div>
      </header>

      {oauthResult ? (
        <div role="status" className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
          {oauthResult === 'success' || oauthResult === 'connected'
            ? t('apps.mcp.oauthConnected')
            : t('apps.mcp.oauthReturned', { status: oauthResult })}
        </div>
      ) : null}

      <McpUsageSummary />

      {query.isLoading ? (
        <div className="space-y-3" data-testid="mcp-servers-loading">
          {[0, 1].map((item) => <div key={item} className="h-36 rounded-xl bg-muted animate-pulse" />)}
        </div>
      ) : null}

      {query.isError ? (
        <Card className="border-destructive/30">
          <CardContent className="p-5 space-y-3">
            <p className="text-sm text-destructive">
              {t(errorMessageKey(query.error instanceof ApiError ? query.error.code : 'unknown'))}
            </p>
            <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
              <RefreshCw className="size-4" aria-hidden />
              {t('apps.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!query.isLoading && !query.isError && items.length === 0 ? (
        <Card data-testid="mcp-servers-empty">
          <CardContent className="p-10 flex flex-col items-center text-center gap-3">
            <Server className="size-9 text-muted-foreground" aria-hidden />
            <h2 className="font-semibold">{t('apps.mcp.emptyTitle')}</h2>
            <p className="text-sm text-muted-foreground max-w-lg">{t('apps.mcp.emptyHint')}</p>
            {canConnect ? <Button type="button" onClick={() => setDialogOpen(true)}>{t('apps.mcp.addServer')}</Button> : null}
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-3">
        {items.map((server) => {
          const requiresReauthorization = Boolean(
            server.reauthorization_required || server.auth.reauthorization_required,
          );
          const status = requiresReauthorization
            ? 'reauthorization_required'
            : displayedServerStatus(server);
          return (
            <Card key={server.id} data-testid="mcp-server-card">
              <CardHeader className="py-3">
                <div className="min-w-0">
                  <h2 className="font-semibold truncate" dir="auto">{serverName(server)}</h2>
                  <p className="text-xs text-muted-foreground truncate" dir="ltr">
                    {server.endpoint_host}
                  </p>
                </div>
                <Badge variant={statusVariant(status)} appearance="light" size="sm">
                  {t(`apps.mcp.status.${status}`, { defaultValue: status })}
                </Badge>
              </CardHeader>
              <CardContent className="space-y-4">
                <dl className="grid gap-3 text-sm sm:grid-cols-3">
                  <div><dt className="text-xs text-muted-foreground">{t('apps.mcp.authentication')}</dt><dd>{t(`apps.mcp.auth.${server.auth.mode}`, { defaultValue: server.auth.mode })}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">{t('apps.mcp.protocol')}</dt><dd dir="ltr">{server.protocol_version || '—'}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">{t('apps.mcp.account')}</dt><dd dir="auto">{server.external_identity_label || server.external_account_name || t('apps.mcp.sharedWorkspaceAccount')}</dd></div>
                </dl>
                {requiresReauthorization ? (
                  <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
                    <ShieldAlert className="size-4 shrink-0" aria-hidden />
                    <span>{t('apps.mcp.reauthorizationWarning')}</span>
                  </div>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <Button asChild size="sm" variant="outline"><Link to={`/apps/mcp/${server.id}`}>{t('apps.mcp.manageTools')}</Link></Button>
                  {server.auth.mode === 'oauth' && canConnect ? (
                    <Button type="button" size="sm" variant="outline" disabled={reauthorize.isPending} onClick={() => void startReauthorization(server)}>{t('apps.mcp.reauthorize')}</Button>
                  ) : null}
                  {canConnect ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={remove.isPending}
                      onClick={() => {
                        setDeleteError(null);
                        setServerToDelete(server);
                      }}
                      data-testid={`mcp-delete-server-${server.id}`}
                    >
                      {t('apps.mcp.deleteServer')}
                    </Button>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <McpServerDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      <DeleteMcpServerDialog
        server={serverToDelete}
        open={serverToDelete !== null}
        onOpenChange={(open) => {
          if (!open) {
            setServerToDelete(null);
            setDeleteError(null);
          }
        }}
        onConfirm={(server) => void removeServer(server)}
        isPending={remove.isPending}
        errorMessage={deleteError}
      />
    </div>
  );
}
