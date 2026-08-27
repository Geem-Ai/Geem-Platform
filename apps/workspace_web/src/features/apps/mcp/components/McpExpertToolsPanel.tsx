import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ShieldAlert, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { WorkspacePermission } from '@/features/authz/permissions';
import { usePermissions } from '@/features/authz/usePermissions';
import { useAppConnections } from '@/features/apps/connections/hooks/useConnectionQueries';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { getChatWidget } from '@/services/api/apps';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { McpGrant, McpSurfaceKind, McpWritePolicy } from '@/services/api/mcp';
import { queryKeys } from '@/services/api/query-keys';
import {
  useCreateExpertMcpGrant,
  useCreateExpertMcpSurfaceBinding,
  useExpertMcpGrants,
  useExpertMcpSurfaceBindings,
  useMcpServers,
  useMcpTools,
  useRevokeExpertMcpGrant,
  useRevokeExpertMcpSurfaceBinding,
} from '../hooks/useMcpQueries';
import { whatsappMcpSurfaceTargets } from '../surfaceTargets';

function grantName(grant: McpGrant): string {
  return grant.tool_name || grant.llm_tool_name || grant.tool_id;
}

export function McpExpertToolsPanel({ expertId }: { expertId: string }) {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const canEdit = can(WorkspacePermission.EXPERTS_UPDATE);
  const [serverId, setServerId] = useState('');
  const [toolId, setToolId] = useState('');
  const [allowChat, setAllowChat] = useState(true);
  const [allowApi, setAllowApi] = useState(false);
  const [unattendedWrite, setUnattendedWrite] = useState(false);
  const [outboundAck, setOutboundAck] = useState(false);
  const [unattendedAck, setUnattendedAck] = useState(false);
  const [bindingGrantId, setBindingGrantId] = useState('');
  const [surfaceKind, setSurfaceKind] = useState<McpSurfaceKind>('chat_widget');
  const [targetId, setTargetId] = useState('');
  const [writePolicy, setWritePolicy] = useState<McpWritePolicy>('deny');
  const [publicAck, setPublicAck] = useState(false);
  const [bindingOutboundAck, setBindingOutboundAck] = useState(false);
  const servers = useMcpServers({ limit: 100, offset: 0 });
  const tools = useMcpTools(serverId || undefined, { limit: 100, offset: 0 });
  const grants = useExpertMcpGrants(expertId);
  const bindings = useExpertMcpSurfaceBindings(expertId);
  const createGrant = useCreateExpertMcpGrant(expertId);
  const revokeGrant = useRevokeExpertMcpGrant(expertId);
  const createBinding = useCreateExpertMcpSurfaceBinding(expertId);
  const revokeBinding = useRevokeExpertMcpSurfaceBinding(expertId);
  const widget = useQuery({
    queryKey: queryKeys.chatWidget(workspaceId),
    queryFn: getChatWidget,
    enabled: Boolean(workspaceId),
    retry: false,
  });
  const whatsapp = useAppConnections('whatsapp', Boolean(workspaceId));
  const selectedTool = tools.data?.items.find((tool) => tool.id === toolId);
  const activeGrants = (grants.data ?? []).filter((grant) => grant.state !== 'revoked');
  const targets = useMemo(() => {
    if (surfaceKind === 'chat_widget') {
      return widget.data ? [{ id: widget.data.id, label: widget.data.title || widget.data.id }] : [];
    }
    return whatsappMcpSurfaceTargets(whatsapp.data?.items ?? []);
  }, [surfaceKind, widget.data, whatsapp.data]);

  useEffect(() => {
    setToolId('');
  }, [serverId]);
  useEffect(() => {
    setTargetId('');
  }, [surfaceKind]);

  async function addGrant() {
    if (!serverId || !toolId || !outboundAck) return;
    try {
      await createGrant.mutateAsync({
        tool_id: toolId,
        allow_workspace_chat: allowChat,
        allow_public_api: allowApi,
        unattended_write_allowed: unattendedWrite,
        outbound_data_acknowledged: outboundAck,
        unattended_write_risk_acknowledged: unattendedWrite ? unattendedAck : false,
      });
      setToolId('');
      setUnattendedWrite(false);
      setUnattendedAck(false);
      toast.success(t('experts.mcp.grantAdded'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  async function removeGrant(grantId: string) {
    try {
      await revokeGrant.mutateAsync(grantId);
      toast.success(t('experts.mcp.grantRevoked'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  async function addBinding() {
    if (!bindingGrantId || !targetId || !publicAck || !bindingOutboundAck) return;
    try {
      await createBinding.mutateAsync({
        mcp_tool_grant_id: bindingGrantId,
        surface_kind: surfaceKind,
        widget_instance_id: surfaceKind === 'chat_widget' ? targetId : null,
        channel_binding_id: surfaceKind === 'whatsapp_openwa' ? targetId : null,
        write_policy: writePolicy,
        public_risk_acknowledged: publicAck,
        outbound_data_acknowledged: bindingOutboundAck,
      });
      setBindingGrantId('');
      setTargetId('');
      setPublicAck(false);
      setBindingOutboundAck(false);
      toast.success(t('experts.mcp.bindingAdded'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  async function removeBinding(bindingId: string) {
    try {
      await revokeBinding.mutateAsync(bindingId);
      toast.success(t('experts.mcp.bindingRevoked'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  return (
    <div className="space-y-5" data-testid="expert-mcp-tools-panel">
      <div className="rounded-lg border border-border bg-muted/30 p-3 flex gap-2 text-xs text-muted-foreground">
        <ShieldAlert className="size-4 shrink-0 text-primary" aria-hidden />
        <span>{t('experts.mcp.securityDisclosure')}</span>
      </div>

      <Card className="rounded-md">
        <CardHeader className="min-h-[38px] bg-accent/50"><div><h3 className="text-sm font-semibold">{t('experts.mcp.addGrant')}</h3><p className="text-xs text-muted-foreground">{t('experts.mcp.addGrantHint')}</p></div></CardHeader>
        <CardContent className="pt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2"><Label>{t('experts.mcp.server')}</Label><Select value={serverId} onValueChange={setServerId} disabled={!canEdit}><SelectTrigger><SelectValue placeholder={t('experts.mcp.selectServer')} /></SelectTrigger><SelectContent>{(servers.data?.items ?? []).map((server) => <SelectItem key={server.id} value={server.id}>{server.display_name || server.endpoint_host || server.id}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-2"><Label>{t('experts.mcp.tool')}</Label><Select value={toolId} onValueChange={setToolId} disabled={!canEdit || !serverId}><SelectTrigger><SelectValue placeholder={t('experts.mcp.selectTool')} /></SelectTrigger><SelectContent>{(tools.data?.items ?? []).filter((tool) => tool.compatibility_status === 'compatible' && tool.status === 'active').map((tool) => <SelectItem key={tool.id} value={tool.id}>{tool.title || tool.tool_name}</SelectItem>)}</SelectContent></Select></div>
          </div>
          {selectedTool?.classification === 'unknown' ? <p className="text-xs text-destructive">{t('experts.mcp.unknownClassificationWarning')}</p> : null}
          <div className="grid gap-2 text-sm sm:grid-cols-2">
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={allowChat} onChange={(event) => setAllowChat(event.target.checked)} disabled={!canEdit} />{t('experts.mcp.workspaceChat')}</label>
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={allowApi} onChange={(event) => setAllowApi(event.target.checked)} disabled={!canEdit} />{t('experts.mcp.publicApi')}</label>
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={unattendedWrite} onChange={(event) => setUnattendedWrite(event.target.checked)} disabled={!canEdit || !allowApi || selectedTool?.classification !== 'write'} />{t('experts.mcp.unattendedWrite')}</label>
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={outboundAck} onChange={(event) => setOutboundAck(event.target.checked)} disabled={!canEdit} />{t('experts.mcp.outboundAck')}</label>
            {unattendedWrite ? <label className="flex items-center gap-2 sm:col-span-2 text-destructive"><input type="checkbox" className="size-4 accent-primary" checked={unattendedAck} onChange={(event) => setUnattendedAck(event.target.checked)} disabled={!canEdit} />{t('experts.mcp.unattendedAck')}</label> : null}
          </div>
          {allowApi ? <p className="text-xs text-muted-foreground">{t('experts.mcp.apiWarning')}</p> : null}
          <Button type="button" size="sm" onClick={() => void addGrant()} disabled={!canEdit || !serverId || !toolId || !outboundAck || (unattendedWrite && !unattendedAck) || createGrant.isPending}>{t('experts.mcp.grant')}</Button>
        </CardContent>
      </Card>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t('experts.mcp.currentGrants')}</h3>
        {grants.isError ? <p className="text-xs text-destructive">{t('experts.mcp.loadError')}</p> : null}
        {activeGrants.length === 0 ? <p className="text-sm text-muted-foreground">{t('experts.mcp.noGrants')}</p> : activeGrants.map((grant) => (
          <div key={grant.id} className="rounded-lg border border-border p-3 flex items-start justify-between gap-3" data-testid="expert-mcp-grant">
            <div className="min-w-0"><p className="text-sm font-medium truncate" dir="auto">{grantName(grant)}</p><div className="flex flex-wrap gap-1 mt-1"><Badge variant={grant.state === 'active' ? 'success' : 'warning'} appearance="light" size="xs">{grant.state}</Badge>{grant.allow_workspace_chat ? <Badge variant="secondary" appearance="light" size="xs">{t('experts.mcp.workspaceChat')}</Badge> : null}{grant.allow_public_api ? <Badge variant="secondary" appearance="light" size="xs">{t('experts.mcp.publicApi')}</Badge> : null}</div></div>
            {canEdit ? <Button type="button" variant="ghost" size="icon" aria-label={t('experts.mcp.revoke')} disabled={revokeGrant.isPending} onClick={() => void removeGrant(grant.id)}><Trash2 className="size-4" aria-hidden /></Button> : null}
          </div>
        ))}
      </div>

      <Card className="rounded-md">
        <CardHeader className="min-h-[38px] bg-accent/50"><div><h3 className="text-sm font-semibold">{t('experts.mcp.surfaceBindings')}</h3><p className="text-xs text-muted-foreground">{t('experts.mcp.surfaceBindingsHint')}</p></div></CardHeader>
        <CardContent className="pt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2"><Label>{t('experts.mcp.grant')}</Label><Select value={bindingGrantId} onValueChange={setBindingGrantId} disabled={!canEdit}><SelectTrigger data-testid="mcp-binding-grant"><SelectValue placeholder={t('experts.mcp.selectGrant')} /></SelectTrigger><SelectContent>{activeGrants.filter((grant) => grant.state === 'active').map((grant) => <SelectItem key={grant.id} value={grant.id}>{grantName(grant)}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-2"><Label>{t('experts.mcp.surface')}</Label><Select value={surfaceKind} onValueChange={(value) => setSurfaceKind(value as McpSurfaceKind)} disabled={!canEdit}><SelectTrigger data-testid="mcp-binding-surface"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="chat_widget">{t('experts.mcp.chatWidget')}</SelectItem><SelectItem value="whatsapp_openwa">{t('experts.mcp.whatsapp')}</SelectItem></SelectContent></Select></div>
            <div className="space-y-2"><Label>{t('experts.mcp.exactTarget')}</Label><Select value={targetId} onValueChange={setTargetId} disabled={!canEdit}><SelectTrigger data-testid="mcp-binding-target"><SelectValue placeholder={t('experts.mcp.selectTarget')} /></SelectTrigger><SelectContent>{targets.map((target) => <SelectItem key={target.id} value={target.id}>{target.label}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-2"><Label>{t('experts.mcp.writePolicy')}</Label><Select value={writePolicy} onValueChange={(value) => setWritePolicy(value as McpWritePolicy)} disabled={!canEdit}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="deny">{t('experts.mcp.writeDeny')}</SelectItem><SelectItem value="workspace_operator_approval">{t('experts.mcp.operatorApproval')}</SelectItem></SelectContent></Select></div>
          </div>
          <div className="space-y-2 text-sm"><label className="flex items-center gap-2 text-destructive"><input type="checkbox" className="size-4 accent-primary" checked={publicAck} onChange={(event) => setPublicAck(event.target.checked)} disabled={!canEdit} />{t('experts.mcp.publicRiskAck')}</label><label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={bindingOutboundAck} onChange={(event) => setBindingOutboundAck(event.target.checked)} disabled={!canEdit} />{t('experts.mcp.outboundAck')}</label></div>
          <Button type="button" size="sm" onClick={() => void addBinding()} disabled={!canEdit || !bindingGrantId || !targetId || !publicAck || !bindingOutboundAck || createBinding.isPending}>{t('experts.mcp.bindSurface')}</Button>
        </CardContent>
      </Card>

      <div className="space-y-2">
        {(bindings.data ?? []).map((binding) => <div key={binding.id} className="rounded-lg border border-border p-3 flex items-center justify-between gap-3" data-testid="expert-mcp-binding"><div><p className="text-sm font-medium" dir="auto">{binding.target_label || binding.widget_instance_id || binding.channel_binding_id}</p><p className="text-xs text-muted-foreground">{t(`experts.mcp.surfaceKind.${binding.surface_kind}`)} · {t(`experts.mcp.writePolicyValue.${binding.write_policy}`)}</p></div>{canEdit ? <Button type="button" variant="ghost" size="icon" aria-label={t('experts.mcp.revoke')} disabled={revokeBinding.isPending} onClick={() => void removeBinding(binding.id)}><Trash2 className="size-4" aria-hidden /></Button> : null}</div>)}
      </div>
    </div>
  );
}
