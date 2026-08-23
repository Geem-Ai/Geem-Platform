import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { GrantAppDialog } from '@/features/app-store/components/GrantAppDialog';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformWorkspaces, platformQueryKeys } from '@/services/api/platform';
import type { PlatformAppDetail, PlatformWorkspaceApp } from '@/services/api/types';

const PICKER_PAGE_SIZE = 8;

type GrantToWorkspacePanelProps = {
  app: PlatformAppDetail;
  onComplete: () => void;
};

export function GrantToWorkspacePanel({ app, onComplete }: GrantToWorkspacePanelProps) {
  const { t } = useTranslation();
  const [pickerSearch, setPickerSearch] = useState('');
  const [pickerOffset, setPickerOffset] = useState(0);
  const [selectedWorkspace, setSelectedWorkspace] = useState<{
    id: string;
    name: string;
  } | null>(null);

  const workspacePickerQuery = useQuery({
    queryKey: platformQueryKeys.workspaces({
      search: pickerSearch.trim() || undefined,
      kind: 'tenant',
      limit: PICKER_PAGE_SIZE,
      offset: pickerOffset,
    }),
    queryFn: () =>
      fetchPlatformWorkspaces({
        search: pickerSearch.trim() || undefined,
        kind: 'tenant',
        limit: PICKER_PAGE_SIZE,
        offset: pickerOffset,
      }),
  });

  const dialogApp = useMemo<PlatformWorkspaceApp | null>(() => {
    if (!selectedWorkspace) return null;
    return {
      app_id: app.id,
      app_slug: app.slug,
      app_name: app.name,
      billing_type: app.billing_type,
      catalog_status: app.status,
      access_status: 'not_entitled',
      installed: false,
      entitlements: {},
    };
  }, [app, selectedWorkspace]);

  const pickerWorkspaces = workspacePickerQuery.data?.items ?? [];

  if (app.billing_type === 'free') {
    return (
      <p className="text-sm text-muted-foreground" data-testid="grant-to-workspace-free-hint">
        {t('appStore.grantFreeHint')}
      </p>
    );
  }

  return (
    <div className="space-y-4 rounded-xl border border-dashed border-border p-4" data-testid="grant-to-workspace-panel">
      <div>
        <p className="text-sm font-medium">{t('appStore.grantToWorkspaceTitle')}</p>
        <p className="text-xs text-muted-foreground">{t('appStore.grantToWorkspaceSubtitle')}</p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="grant-workspace-search">{t('appStore.grantToWorkspaceSearch')}</Label>
        <Input
          id="grant-workspace-search"
          value={pickerSearch}
          onChange={(e) => {
            setPickerSearch(e.target.value);
            setPickerOffset(0);
          }}
          placeholder={t('appStore.grantToWorkspaceSearchPlaceholder')}
          data-testid="grant-workspace-search"
        />
      </div>

      {workspacePickerQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : null}

      {workspacePickerQuery.isError ? (
        <p className="text-sm text-destructive">{getErrorMessage(workspacePickerQuery.error, t)}</p>
      ) : null}

      {pickerWorkspaces.map((ws) => (
        <div
          key={ws.id}
          className="flex items-center justify-between rounded-lg border border-border p-3"
          data-testid={`grant-workspace-row-${ws.id}`}
        >
          <div>
            <p className="font-medium">{ws.name}</p>
            <p className="text-xs text-muted-foreground">{ws.slug}</p>
          </div>
          <Button
            size="sm"
            onClick={() => setSelectedWorkspace({ id: ws.id, name: ws.name })}
            data-testid={`grant-workspace-button-${ws.id}`}
          >
            {t('appStore.grant')}
          </Button>
        </div>
      ))}

      {!workspacePickerQuery.isLoading &&
      !workspacePickerQuery.isError &&
      pickerWorkspaces.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="grant-workspace-empty">
          {pickerSearch.trim()
            ? t('appStore.grantToWorkspaceEmpty')
            : t('appStore.grantToWorkspaceNoTenants')}
        </p>
      ) : null}

      {workspacePickerQuery.data && workspacePickerQuery.data.total > PICKER_PAGE_SIZE ? (
        <AdminPagination
          total={workspacePickerQuery.data.total}
          limit={workspacePickerQuery.data.limit}
          offset={workspacePickerQuery.data.offset}
          onPageChange={setPickerOffset}
          testId="grant-workspace-pagination"
        />
      ) : null}

      <GrantAppDialog
        open={Boolean(selectedWorkspace)}
        onOpenChange={(open) => !open && setSelectedWorkspace(null)}
        workspaceId={selectedWorkspace?.id ?? ''}
        workspaceName={selectedWorkspace?.name}
        app={dialogApp}
        plans={app.plans}
        mode="grant"
        onComplete={() => {
          setSelectedWorkspace(null);
          onComplete();
        }}
      />
    </div>
  );
}
