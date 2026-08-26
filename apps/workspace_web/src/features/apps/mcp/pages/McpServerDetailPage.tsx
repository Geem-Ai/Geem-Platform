import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Search, ShieldAlert, Wrench, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { WorkspacePermission } from '@/features/authz/permissions';
import { usePermissions } from '@/features/authz/usePermissions';
import { useExperts } from '@/features/experts/hooks/useExperts';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { McpGrant, McpTool, McpToolClassification } from '@/services/api/mcp';
import {
  useCreateExpertMcpGrant,
  useDiscoverMcpTools,
  useExpertMcpGrants,
  useMcpServer,
  useMcpTools,
  useRevokeExpertMcpGrant,
  useUpdateMcpToolClassification,
} from '../hooks/useMcpQueries';

const PAGE_SIZE = 25;

function toolLabel(tool: McpTool): string {
  return tool.title || tool.tool_name;
}

export function McpServerDetailPage() {
  const { t } = useTranslation();
  const { connectionId = '' } = useParams<{ connectionId: string }>();
  const { can } = usePermissions();
  const [offset, setOffset] = useState(0);
  const [toolSearchInput, setToolSearchInput] = useState('');
  const [toolSearch, setToolSearch] = useState('');
  const [expertId, setExpertId] = useState('');
  const [allowWorkspaceChat, setAllowWorkspaceChat] = useState(true);
  const [allowPublicApi, setAllowPublicApi] = useState(false);
  const [outboundAck, setOutboundAck] = useState(false);
  const [savingGrantToolId, setSavingGrantToolId] = useState<string | null>(null);
  const [revokingGrantId, setRevokingGrantId] = useState<string | null>(null);
  const serverQuery = useMcpServer(connectionId);
  const toolsQuery = useMcpTools(connectionId, {
    limit: PAGE_SIZE,
    offset,
    q: toolSearch,
  });
  const expertsQuery = useExperts();
  const grantsQuery = useExpertMcpGrants(expertId || undefined);
  const discover = useDiscoverMcpTools();
  const classify = useUpdateMcpToolClassification(connectionId);
  const createGrant = useCreateExpertMcpGrant(expertId);
  const revokeGrant = useRevokeExpertMcpGrant(expertId);
  const canManageApps = can(WorkspacePermission.APPS_MANAGE);
  const canUpdateExperts = can(WorkspacePermission.EXPERTS_UPDATE);
  const workspaceExperts = (expertsQuery.data ?? []).filter((expert) => expert.ownership === 'workspace');
  const grantedToolIds = useMemo(
    () => new Map((grantsQuery.data ?? []).map((grant) => [grant.tool_id, grant])),
    [grantsQuery.data],
  );
  const server = serverQuery.data;
  const tools = toolsQuery.data?.items ?? [];

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const next = toolSearchInput.trim();
      if (next === toolSearch) return;
      setOffset(0);
      setToolSearch(next);
    }, 300);
    return () => window.clearTimeout(handle);
  }, [toolSearch, toolSearchInput]);

  function clearToolSearch() {
    setToolSearchInput('');
    setToolSearch('');
    setOffset(0);
  }

  async function refreshDiscovery() {
    try {
      const result = await discover.mutateAsync(connectionId);
      toast.success(t('apps.mcp.discoveryComplete', { count: result.tools_seen }));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  async function updateClassification(tool: McpTool, classification: McpToolClassification) {
    try {
      await classify.mutateAsync({ toolId: tool.id, classification });
      toast.success(t('apps.mcp.classificationUpdated'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  async function saveGrant(tool: McpTool, existingGrant?: McpGrant) {
    if (!expertId) return;
    setSavingGrantToolId(tool.id);
    try {
      await createGrant.mutateAsync({
        tool_id: tool.id,
        allow_workspace_chat: allowWorkspaceChat,
        allow_public_api: allowPublicApi,
        unattended_write_allowed: false,
        outbound_data_acknowledged: outboundAck,
      });
      if (!existingGrant) {
        toast.success(t('experts.mcp.grantAdded'));
      } else if (existingGrant.state === 'active') {
        toast.success(t('experts.mcp.grantUpdated'));
      } else {
        toast.success(t('experts.mcp.grantReapproved'));
      }
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    } finally {
      setSavingGrantToolId(null);
    }
  }

  async function revokeToolGrant(grant: McpGrant) {
    setRevokingGrantId(grant.id);
    try {
      await revokeGrant.mutateAsync(grant.id);
      toast.success(t('experts.mcp.grantRevoked'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    } finally {
      setRevokingGrantId(null);
    }
  }

  const loadError = serverQuery.error || toolsQuery.error;

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-6 ms-auto me-auto" data-testid="mcp-server-detail-page">
      <DocumentTitle title={server?.display_name || t('apps.mcp.serverDetails')} />
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1 min-w-0">
          <Button asChild variant="ghost" size="sm" className="-ms-2 mb-1">
            <Link to="/apps/mcp"><ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />{t('apps.mcp.backToServers')}</Link>
          </Button>
          <h1 className="text-2xl font-semibold tracking-tight truncate" dir="auto">{server?.display_name || t('apps.mcp.serverDetails')}</h1>
          <p className="text-sm text-muted-foreground truncate" dir="ltr">{server?.endpoint_host}</p>
        </div>
        {canManageApps ? (
          <Button type="button" variant="outline" size="sm" onClick={() => void refreshDiscovery()} disabled={discover.isPending}>
            <RefreshCw className={`size-4 ${discover.isPending ? 'animate-spin' : ''}`} aria-hidden />
            {t('apps.mcp.discoverTools')}
          </Button>
        ) : null}
      </header>

      {loadError ? (
        <Card className="border-destructive/30"><CardContent className="p-5 text-sm text-destructive">{t(errorMessageKey(loadError instanceof ApiError ? loadError.code : 'unknown'))}</CardContent></Card>
      ) : null}

      {server ? (
        <Card>
          <CardContent className="p-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
            <div><p className="text-xs text-muted-foreground">{t('apps.mcp.health')}</p><p>{t(`apps.mcp.status.${server.health || server.status}`, { defaultValue: server.health || server.status })}</p></div>
            <div><p className="text-xs text-muted-foreground">{t('apps.mcp.protocol')}</p><p dir="ltr">{server.protocol_version || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">{t('apps.mcp.sessionMode')}</p><p>{server.session_mode || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">{t('apps.mcp.account')}</p><p dir="auto">{server.external_identity_label || server.external_account_name || t('apps.mcp.sharedWorkspaceAccount')}</p></div>
          </CardContent>
        </Card>
      ) : null}

      {canUpdateExperts ? (
        <Card data-testid="mcp-grant-controls">
          <CardHeader><div><h2 className="font-semibold">{t('experts.mcp.grantOptions')}</h2><p className="text-xs text-muted-foreground">{t('experts.mcp.grantOptionsHint')}</p></div></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2"><Label>{t('experts.mcp.expert')}</Label><Select value={expertId} onValueChange={setExpertId}><SelectTrigger data-testid="mcp-expert-select"><SelectValue placeholder={t('experts.mcp.selectExpert')} /></SelectTrigger><SelectContent>{workspaceExperts.map((expert) => <SelectItem key={expert.id} value={expert.id}>{expert.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={allowWorkspaceChat} onChange={(event) => setAllowWorkspaceChat(event.target.checked)} />{t('experts.mcp.workspaceChat')}</label>
                <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={allowPublicApi} onChange={(event) => setAllowPublicApi(event.target.checked)} />{t('experts.mcp.publicApi')}</label>
                <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={outboundAck} onChange={(event) => setOutboundAck(event.target.checked)} />{t('experts.mcp.outboundAck')}</label>
              </div>
            </div>
            {allowPublicApi ? <p className="text-xs text-muted-foreground">{t('experts.mcp.apiWarning')}</p> : null}
          </CardContent>
        </Card>
      ) : null}

      <section className="space-y-3" aria-labelledby="mcp-tools-heading">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div><h2 id="mcp-tools-heading" className="text-lg font-semibold">{t('apps.mcp.tools')}</h2><p className="text-sm text-muted-foreground">{t('apps.mcp.toolsHint')}</p></div>
          <div className="relative w-full sm:w-64 shrink-0">
            <Search className="pointer-events-none absolute start-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              value={toolSearchInput}
              onChange={(event) => setToolSearchInput(event.target.value)}
              placeholder={t('apps.mcp.toolsSearchPlaceholder')}
              aria-label={t('apps.mcp.toolsSearchPlaceholder')}
              data-testid="mcp-tools-search"
              className="ps-8 pe-8"
              maxLength={200}
            />
            {toolSearchInput ? (
              <button
                type="button"
                onClick={clearToolSearch}
                className="absolute end-2 top-1/2 -translate-y-1/2 rounded-sm text-muted-foreground hover:text-foreground"
                aria-label={t('apps.mcp.clearToolsSearch')}
                data-testid="mcp-tools-search-clear"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            ) : null}
          </div>
        </div>
        {toolsQuery.isLoading ? <div className="h-36 rounded-xl bg-muted animate-pulse" /> : null}
        {!toolsQuery.isLoading && tools.length === 0 ? <Card><CardContent className="p-8 text-center text-sm text-muted-foreground"><Wrench className="size-7 mx-auto mb-2" aria-hidden />{toolSearch ? t('apps.mcp.noToolsMatch', { query: toolSearch }) : t('apps.mcp.noTools')}</CardContent></Card> : null}
        {tools.map((tool) => {
          const grantRecord = grantedToolIds.get(tool.id);
          const existingGrant = grantRecord?.state === 'revoked' ? undefined : grantRecord;
          const incompatible = tool.compatibility_status !== 'compatible';
          const stale = tool.status !== 'active';
          const unclassified = tool.classification === 'unknown';
          const reauthorizationRequired = Boolean(
            server?.reauthorization_required || server?.auth?.reauthorization_required,
          );
          const savingGrant = savingGrantToolId === tool.id;
          const revokingGrant = existingGrant ? revokingGrantId === existingGrant.id : false;
          const grantAction = !existingGrant
            ? 'grant'
            : existingGrant.state === 'active'
              ? 'saveGrantChanges'
              : 'reapprove';
          const pendingGrantAction = !existingGrant
            ? 'granting'
            : existingGrant.state === 'active'
              ? 'savingGrantChanges'
              : 'reapproving';
          const grantActionDisabled =
            incompatible
            || stale
            || unclassified
            || reauthorizationRequired
            || (!allowWorkspaceChat && !allowPublicApi)
            || !outboundAck
            || Boolean(grantsQuery.isLoading)
            || createGrant.isPending
            || revokeGrant.isPending;
          return (
            <Card key={tool.id} data-testid="mcp-tool-card" aria-busy={savingGrant || revokingGrant}>
              <CardHeader className="py-3">
                <div className="min-w-0"><h3 className="font-semibold truncate" dir="auto">{toolLabel(tool)}</h3><p className="font-mono text-xs text-muted-foreground truncate" dir="ltr">{tool.tool_name} · {tool.llm_tool_name}</p></div>
                <div className="flex gap-1.5"><Badge variant={incompatible ? 'destructive' : 'success'} appearance="light" size="sm">{t(`apps.mcp.compatibility.${tool.compatibility_status}`, { defaultValue: tool.compatibility_status })}</Badge>{stale ? <Badge variant="warning" appearance="light" size="sm">{t(`apps.mcp.toolStatus.${tool.status}`, { defaultValue: tool.status })}</Badge> : null}</div>
              </CardHeader>
              <CardContent className="space-y-3">
                {tool.description ? <p className="text-sm text-muted-foreground" dir="auto">{tool.description}</p> : null}
                {incompatible && tool.compatibility_reason ? <div className="flex gap-2 text-xs text-destructive"><ShieldAlert className="size-4 shrink-0" aria-hidden />{tool.compatibility_reason}</div> : null}
                <div className="flex flex-wrap items-end gap-3">
                  <div className="space-y-1"><Label>{t('apps.mcp.classification')}</Label><Select value={tool.classification} disabled={!canManageApps || classify.isPending} onValueChange={(value) => void updateClassification(tool, value as McpToolClassification)}><SelectTrigger className="w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="read_only">{t('apps.mcp.classifications.read_only')}</SelectItem><SelectItem value="write">{t('apps.mcp.classifications.write')}</SelectItem><SelectItem value="unknown">{t('apps.mcp.classifications.unknown')}</SelectItem></SelectContent></Select></div>
                  {canUpdateExperts && expertId ? (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant={existingGrant ? 'primary' : 'outline'}
                        disabled={grantActionDisabled}
                        onClick={() => void saveGrant(tool, existingGrant)}
                        aria-label={t('experts.mcp.toolGrantActionLabel', {
                          action: t(`experts.mcp.${grantAction}`),
                          tool: toolLabel(tool),
                        })}
                      >
                        {t(`experts.mcp.${savingGrant ? pendingGrantAction : grantAction}`)}
                      </Button>
                      {existingGrant ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="destructive"
                          disabled={createGrant.isPending || revokeGrant.isPending}
                          onClick={() => void revokeToolGrant(existingGrant)}
                          aria-label={t('experts.mcp.toolGrantActionLabel', {
                            action: t('experts.mcp.revoke'),
                            tool: toolLabel(tool),
                          })}
                        >
                          {t(`experts.mcp.${revokingGrant ? 'revoking' : 'revoke'}`)}
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                {existingGrant && existingGrant.state !== 'active' ? <p className="text-xs text-destructive">{t('experts.mcp.grantStateWarning', { state: existingGrant.state })}</p> : null}
              </CardContent>
            </Card>
          );
        })}
        {(toolsQuery.data?.total ?? 0) > PAGE_SIZE ? <div className="flex justify-between"><Button type="button" variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>{t('common.previous')}</Button><span className="text-xs text-muted-foreground self-center">{t('apps.mcp.pagination', { from: offset + 1, to: Math.min(offset + PAGE_SIZE, toolsQuery.data?.total ?? 0), total: toolsQuery.data?.total ?? 0 })}</span><Button type="button" variant="outline" size="sm" disabled={offset + PAGE_SIZE >= (toolsQuery.data?.total ?? 0)} onClick={() => setOffset(offset + PAGE_SIZE)}>{t('common.next')}</Button></div> : null}
      </section>
    </div>
  );
}
