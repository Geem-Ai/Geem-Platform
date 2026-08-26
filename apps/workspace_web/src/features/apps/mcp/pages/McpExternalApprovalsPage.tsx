import { Link } from 'react-router-dom';
import { ArrowLeft, CircleAlert, RefreshCw, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import {
  useDecideMcpExternalApproval,
  useMcpExternalApprovals,
  useMcpUnknownDeliveries,
  useReconcileMcpExternalDelivery,
} from '../hooks/useMcpQueries';

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return '{}';
  }
}

export function McpExternalApprovalsPage() {
  const { t, i18n } = useTranslation();
  const approvals = useMcpExternalApprovals();
  const deliveries = useMcpUnknownDeliveries();
  const decide = useDecideMcpExternalApproval();
  const reconcile = useReconcileMcpExternalDelivery();
  const formatDate = (value?: string | null) => value
    ? new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
    : '—';

  async function decideApproval(approvalId: string, decision: 'approve' | 'deny') {
    try {
      await decide.mutateAsync({ approvalId, decision });
      toast.success(t(decision === 'approve' ? 'apps.mcp.externalApprovals.approved' : 'apps.mcp.externalApprovals.denied'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  async function resolveDelivery(deliveryId: string, resolution: 'confirmed_sent' | 'cancelled') {
    try {
      await reconcile.mutateAsync({ deliveryId, resolution });
      toast.success(t('apps.mcp.externalApprovals.reconciled'));
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    }
  }

  const loadError = approvals.error || deliveries.error;

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto" data-testid="mcp-external-approvals-page">
      <DocumentTitle title={t('apps.mcp.externalApprovals.title')} />
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ms-2 mb-1"><Link to="/apps/mcp"><ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />{t('apps.mcp.backToServers')}</Link></Button>
          <h1 className="text-2xl font-semibold tracking-tight">{t('apps.mcp.externalApprovals.title')}</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">{t('apps.mcp.externalApprovals.description')}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => { void approvals.refetch(); void deliveries.refetch(); }} disabled={approvals.isFetching || deliveries.isFetching}>
          <RefreshCw className={`size-4 ${approvals.isFetching || deliveries.isFetching ? 'animate-spin' : ''}`} aria-hidden />{t('apps.refresh')}
        </Button>
      </header>

      {loadError ? <Card className="border-destructive/30"><CardContent className="p-5 text-sm text-destructive">{t(errorMessageKey(loadError instanceof ApiError ? loadError.code : 'unknown'))}</CardContent></Card> : null}

      <section className="space-y-3" aria-labelledby="pending-approvals-heading">
        <div className="flex items-center gap-2"><ShieldCheck className="size-5 text-primary" aria-hidden /><h2 id="pending-approvals-heading" className="text-lg font-semibold">{t('apps.mcp.externalApprovals.pending')}</h2><Badge variant="secondary" appearance="light">{approvals.data?.total ?? 0}</Badge></div>
        {approvals.isLoading ? <div className="h-36 rounded-xl bg-muted animate-pulse" /> : null}
        {!approvals.isLoading && (approvals.data?.items.length ?? 0) === 0 ? <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">{t('apps.mcp.externalApprovals.empty')}</CardContent></Card> : null}
        {(approvals.data?.items ?? []).map((approval) => (
          <Card key={approval.id} data-testid="mcp-external-approval">
            <CardHeader className="py-3">
              <div><h3 className="font-semibold" dir="auto">{approval.tool_name || t('apps.mcp.externalApprovals.toolCall')}</h3><p className="text-xs text-muted-foreground" dir="auto">{approval.connection_name || approval.surface_label}</p></div>
              <Badge variant="warning" appearance="light" size="sm">{t(`apps.mcp.externalApprovals.status.${approval.status}`, { defaultValue: approval.status })}</Badge>
            </CardHeader>
            <CardContent className="space-y-4">
              <dl className="grid gap-3 text-sm sm:grid-cols-3"><div><dt className="text-xs text-muted-foreground">{t('apps.mcp.externalApprovals.surface')}</dt><dd dir="auto">{approval.surface_label}</dd></div><div><dt className="text-xs text-muted-foreground">{t('apps.mcp.externalApprovals.sender')}</dt><dd dir="auto">{approval.sender_label || '—'}</dd></div><div><dt className="text-xs text-muted-foreground">{t('apps.mcp.externalApprovals.expires')}</dt><dd>{formatDate(approval.expires_at)}</dd></div></dl>
              <div><p className="text-xs font-medium mb-1.5">{t('apps.mcp.externalApprovals.exactArguments')}</p><pre className="max-h-64 overflow-auto rounded-lg border border-border bg-muted/40 p-3 text-xs whitespace-pre-wrap break-all" dir="ltr" data-testid="mcp-approval-arguments">{formatJson(approval.arguments)}</pre></div>
              <p className="text-xs text-muted-foreground">{t('apps.mcp.externalApprovals.disclosure')}</p>
              <div className="flex gap-2"><Button type="button" size="sm" disabled={decide.isPending} onClick={() => void decideApproval(approval.id, 'approve')}>{t('apps.mcp.externalApprovals.approve')}</Button><Button type="button" size="sm" variant="destructive" disabled={decide.isPending} onClick={() => void decideApproval(approval.id, 'deny')}>{t('apps.mcp.externalApprovals.deny')}</Button></div>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="space-y-3" aria-labelledby="unknown-deliveries-heading">
        <div className="flex items-center gap-2"><CircleAlert className="size-5 text-destructive" aria-hidden /><h2 id="unknown-deliveries-heading" className="text-lg font-semibold">{t('apps.mcp.externalApprovals.unknownDeliveries')}</h2><Badge variant="destructive" appearance="light">{deliveries.data?.total ?? 0}</Badge></div>
        <p className="text-sm text-muted-foreground">{t('apps.mcp.externalApprovals.unknownHint')}</p>
        {!deliveries.isLoading && (deliveries.data?.items.length ?? 0) === 0 ? <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">{t('apps.mcp.externalApprovals.noUnknownDeliveries')}</CardContent></Card> : null}
        {(deliveries.data?.items ?? []).map((delivery) => (
          <Card key={delivery.id} data-testid="mcp-unknown-delivery"><CardContent className="p-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium" dir="auto">{delivery.surface_label}</p><p className="text-xs text-muted-foreground">{formatDate(delivery.updated_at || delivery.created_at)} · {delivery.provider_message_id || delivery.id}</p></div><div className="flex gap-2"><Button type="button" size="sm" variant="outline" disabled={reconcile.isPending} onClick={() => void resolveDelivery(delivery.id, 'confirmed_sent')}>{t('apps.mcp.externalApprovals.confirmSent')}</Button><Button type="button" size="sm" variant="destructive" disabled={reconcile.isPending} onClick={() => void resolveDelivery(delivery.id, 'cancelled')}>{t('apps.mcp.externalApprovals.cancelDelivery')}</Button></div></CardContent></Card>
        ))}
      </section>
    </div>
  );
}
