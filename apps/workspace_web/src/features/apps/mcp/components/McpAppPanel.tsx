import { Link } from 'react-router-dom';
import { ShieldCheck, Workflow } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { CatalogApp } from '@/services/api/apps';
import { McpUsageSummary } from './McpUsageSummary';
import { usePermissions } from '@/features/authz/usePermissions';
import { WorkspacePermission } from '@/features/authz/permissions';

export function McpAppPanel({ app }: { app: CatalogApp }) {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const installed = app.installation_status === 'active';
  const active = app.access?.status === 'active' && installed;

  if (app.status !== 'published') {
    return (
      <div
        role="note"
        className="rounded-xl border border-border bg-muted/30 px-4 py-3 space-y-2"
        data-testid="mcp-coming-soon"
      >
        <p className="text-sm font-medium">{t('apps.mcp.comingSoonTitle')}</p>
        <p className="text-sm text-muted-foreground">
          {t('apps.mcp.comingSoonHint')}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="mcp-app-panel">
      <div className="rounded-xl border border-border bg-muted/20 px-4 py-3 space-y-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-primary" aria-hidden />
          <p className="text-sm font-semibold">{t('apps.mcp.securityTitle')}</p>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {t('apps.mcp.securityHint')}
        </p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {t('apps.mcp.noTierSwitch')}
        </p>
      </div>

      {active ? <McpUsageSummary /> : null}

      {installed ? (
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link to="/apps/mcp">
              <Workflow className="size-3.5" aria-hidden />
              {t('apps.mcp.manageServers')}
            </Link>
          </Button>
          {can(WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL) ? (
            <Button asChild size="sm" variant="outline">
              <Link to="/apps/mcp/external-approvals">
                {t('apps.mcp.externalApprovals.title')}
              </Link>
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
