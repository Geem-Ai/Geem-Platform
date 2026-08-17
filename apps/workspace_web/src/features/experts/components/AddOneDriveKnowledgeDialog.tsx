import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAppConnections } from '@/features/apps/connections/hooks/useConnectionQueries';
import { useApp } from '@/features/apps/hooks/useAppsQueries';
import {
  openOneDrivePicker,
  type OneDrivePickerSelectedFile,
} from '@/features/apps/microsoft-onedrive/picker';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  createMicrosoftOneDrivePickerSession,
  createMicrosoftOneDrivePickerToken,
} from '@/services/api/apps';
import { createExpertConnectorSources } from '@/services/api/experts';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';

const ONEDRIVE_SLUG = 'microsoft-onedrive';

type Props = {
  expertId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Expert → Add from Microsoft OneDrive.
 * Picker tokens stay memory-only for this dialog session.
 */
export function AddOneDriveKnowledgeDialog({
  expertId,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const appQuery = useApp(ONEDRIVE_SLUG, open);
  const connectionsQuery = useAppConnections(ONEDRIVE_SLUG, open);
  const [connectionId, setConnectionId] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const handoffRef = useRef(false);

  const installed = appQuery.data?.installation_status === 'active';
  const activeConnections =
    connectionsQuery.data?.items.filter(
      (c) => c.status === 'active' || c.status === 'degraded',
    ) ?? [];

  const selectedId =
    connectionId ||
    (activeConnections.length === 1 ? activeConnections[0].id : '');

  async function submitSelection(
    connId: string,
    files: OneDrivePickerSelectedFile[],
  ) {
    if (!connId || files.length === 0) return;
    try {
      await createExpertConnectorSources(expertId, {
        connection_id: connId,
        items: files.map((f) => ({
          external_id: `${f.driveId}:${f.itemId}`,
          provider_locator: {
            drive_id: f.driveId,
            item_id: f.itemId,
          },
        })),
      });
      toast.success(t('experts.oneDrive.added'));
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertKnowledge(workspaceId, expertId),
      });
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
      } else {
        toast.error(t('errors.generic'));
      }
    }
  }

  async function handleOpenPicker() {
    if (!selectedId) return;
    const connId = selectedId;
    setBusy(true);
    setErrorKey(null);
    handoffRef.current = true;
    try {
      const session = await createMicrosoftOneDrivePickerSession(connId);
      onOpenChange(false);
      handoffRef.current = false;
      setBusy(false);
      await openOneDrivePicker({
        session: {
          accessToken: session.access_token,
          baseUrl: session.base_url,
          clientId: session.client_id,
          tenant: session.tenant,
          driveId: session.drive_id,
          getResourceToken: async (resource: string) => {
            const token = await createMicrosoftOneDrivePickerToken(connId, {
              resource,
            });
            return token.access_token;
          },
        },
        multiSelect: true,
        onPicked: (files) => {
          void submitSelection(connId, files);
        },
      });
    } catch (err) {
      handoffRef.current = false;
      setBusy(false);
      if (err instanceof ApiError) {
        setErrorKey(errorMessageKey(err.code));
        toast.error(t(errorMessageKey(err.code)));
      } else if (err instanceof Error && err.message === 'popup_blocked') {
        setErrorKey('experts.oneDrive.popupBlocked');
        toast.error(t('experts.oneDrive.popupBlocked'));
      } else {
        toast.error(t('errors.generic'));
      }
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (handoffRef.current && !next) return;
        onOpenChange(next);
      }}
    >
      <DialogContent data-testid="add-onedrive-knowledge-dialog">
        <DialogHeader>
          <DialogTitle>{t('experts.oneDrive.addTitle')}</DialogTitle>
          <DialogDescription>{t('experts.oneDrive.addHint')}</DialogDescription>
        </DialogHeader>

        {!installed && (
          <div className="space-y-3 text-sm">
            <p>{t('experts.oneDrive.installFirst')}</p>
            <Button asChild variant="secondary">
              <Link to="/apps/microsoft-onedrive">
                {t('experts.oneDrive.goToAppStore')}
              </Link>
            </Button>
          </div>
        )}

        {installed && activeConnections.length === 0 && (
          <div className="space-y-3 text-sm">
            <p>{t('experts.oneDrive.connectFirst')}</p>
            <Button asChild variant="secondary">
              <Link to="/apps/microsoft-onedrive">
                {t('experts.oneDrive.connect')}
              </Link>
            </Button>
          </div>
        )}

        {installed && activeConnections.length > 0 && (
          <div className="space-y-3">
            {activeConnections.length > 1 && (
              <label className="block space-y-1 text-sm">
                <span className="text-muted-foreground">
                  {t('experts.oneDrive.chooseAccount')}
                </span>
                <select
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  value={selectedId}
                  onChange={(e) => setConnectionId(e.target.value)}
                  data-testid="onedrive-connection-select"
                >
                  <option value="">{t('experts.oneDrive.chooseAccount')}</option>
                  {activeConnections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.external_account_name || c.display_name || c.id}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {activeConnections.length === 1 && (
              <p className="text-sm text-muted-foreground">
                {t('experts.oneDrive.connectedAs', {
                  account:
                    activeConnections[0].external_account_name ||
                    activeConnections[0].display_name ||
                    '',
                })}
              </p>
            )}
            {errorKey && (
              <p className="text-sm text-destructive">{t(errorKey)}</p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          {installed && activeConnections.length > 0 && (
            <Button
              onClick={() => void handleOpenPicker()}
              disabled={!selectedId || busy}
              data-testid="onedrive-open-picker"
            >
              {busy
                ? t('experts.oneDrive.openingPicker')
                : t('experts.oneDrive.chooseFiles')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
