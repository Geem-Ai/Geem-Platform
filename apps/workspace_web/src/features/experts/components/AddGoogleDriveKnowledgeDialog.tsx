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
import { OauthAccountActions } from '@/features/apps/connections/components/OauthAccountActions';
import {
  useAppConnections,
  useStartConnection,
} from '@/features/apps/connections/hooks/useConnectionQueries';
import { useApp } from '@/features/apps/hooks/useAppsQueries';
import {
  openGooglePicker,
  type GooglePickerSelectedFile,
} from '@/features/apps/google-drive/picker';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { createGoogleDrivePickerSession } from '@/services/api/apps';
import { createExpertConnectorSources } from '@/services/api/experts';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';

const GOOGLE_DRIVE_SLUG = 'google-drive';

type Props = {
  expertId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Expert → Add from Google Drive.
 * Picker access token stays memory-only for this dialog session.
 *
 * Google Picker renders outside our Dialog DOM. While our dialog stays open,
 * Radix treats Picker clicks as "outside" and dismisses — which drops focus
 * and breaks Select. We close Geem's dialog before showing Picker, and block
 * dismiss during the brief handoff.
 */
export function AddGoogleDriveKnowledgeDialog({
  expertId,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const appQuery = useApp(GOOGLE_DRIVE_SLUG, open);
  const connectionsQuery = useAppConnections(GOOGLE_DRIVE_SLUG, open);
  const startMut = useStartConnection();
  const [connectionId, setConnectionId] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  /** True from session fetch until Geem dialog is closed for Picker. */
  const handoffRef = useRef(false);

  const installed = appQuery.data?.installation_status === 'active';
  const activeConnections =
    connectionsQuery.data?.items.filter(
      (c) => c.status === 'active' || c.status === 'degraded',
    ) ?? [];

  const selectedId =
    connectionId ||
    (activeConnections.length === 1 ? activeConnections[0].id : '');
  const selectedConnection =
    activeConnections.find((c) => c.id === selectedId) ?? activeConnections[0];
  const reconnectable = connectionsQuery.data?.items.find(
    (c) => c.capabilities.can_reconnect,
  );

  function handleConnectAccount() {
    startMut.mutate(
      {
        slug: GOOGLE_DRIVE_SLUG,
        connectionId: reconnectable?.id,
        returnPath: `/experts/${expertId}`,
      },
      {
        onSuccess: (data) => {
          if (data.authorization_url) {
            window.location.assign(data.authorization_url);
          }
        },
      },
    );
  }

  async function submitSelection(
    connId: string,
    files: GooglePickerSelectedFile[],
  ) {
    if (!connId || files.length === 0) return;
    try {
      await createExpertConnectorSources(expertId, {
        connection_id: connId,
        items: files.map((f) => ({
          external_id: f.id,
          resource_key: f.resourceKey ?? null,
        })),
      });
      toast.success(t('experts.googleDrive.added'));
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
      const session = await createGoogleDrivePickerSession(connId);
      // Close before Google overlay mounts so Radix cannot steal dismiss/focus.
      onOpenChange(false);
      handoffRef.current = false;
      setBusy(false);
      await openGooglePicker({
        session: {
          accessToken: session.access_token,
          appId: session.app_id,
          developerKey: session.developer_key,
        },
        multiSelect: true,
        onPicked: (files) => {
          void submitSelection(connId, files);
        },
      });
    } catch (err) {
      handoffRef.current = false;
      if (err instanceof ApiError) {
        setErrorKey(errorMessageKey(err.code));
        toast.error(t(errorMessageKey(err.code)));
      } else {
        setErrorKey('errors.generic');
        toast.error(t('errors.generic'));
      }
      setBusy(false);
    }
  }

  function blockDismissWhileHandoff(event: Event) {
    if (busy || handoffRef.current) {
      event.preventDefault();
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Ignore backdrop/escape dismiss during session fetch → Picker handoff.
        if (!next && (busy || handoffRef.current)) return;
        onOpenChange(next);
      }}
    >
      <DialogContent
        data-testid="google-drive-knowledge-dialog"
        onPointerDownOutside={blockDismissWhileHandoff}
        onInteractOutside={blockDismissWhileHandoff}
        onFocusOutside={blockDismissWhileHandoff}
        onEscapeKeyDown={blockDismissWhileHandoff}
      >
        <DialogHeader>
          <DialogTitle>{t('experts.googleDrive.addTitle')}</DialogTitle>
          <DialogDescription>
            {t('experts.googleDrive.addHint')}
          </DialogDescription>
        </DialogHeader>

        {!installed ? (
          <div className="space-y-3" data-testid="google-drive-not-installed">
            <p className="text-sm text-muted-foreground">
              {t('experts.googleDrive.installFirst')}
            </p>
            <Button asChild size="sm">
              <Link to="/apps/google-drive">{t('experts.googleDrive.goToAppStore')}</Link>
            </Button>
          </div>
        ) : activeConnections.length === 0 ? (
          <div className="space-y-3" data-testid="google-drive-not-connected">
            <p className="text-sm text-muted-foreground">
              {t('experts.googleDrive.connectFirst')}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={startMut.isPending}
                onClick={handleConnectAccount}
                data-testid="google-drive-connect-account"
              >
                {t('experts.googleDrive.connect')}
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link to="/apps/google-drive">
                  {t('experts.googleDrive.goToAppStore')}
                </Link>
              </Button>
            </div>
            {startMut.isError ? (
              <p className="text-sm text-destructive">
                {t(
                  errorMessageKey(
                    startMut.error instanceof ApiError
                      ? startMut.error.code
                      : 'unknown',
                  ),
                )}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="space-y-3">
            {activeConnections.length > 1 ? (
              <div className="space-y-1.5">
                <label
                  htmlFor="google-drive-connection"
                  className="text-sm font-medium"
                >
                  {t('experts.googleDrive.chooseAccount')}
                </label>
                <select
                  id="google-drive-connection"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs"
                  value={selectedId}
                  onChange={(e) => setConnectionId(e.target.value)}
                  data-testid="google-drive-connection-select"
                >
                  <option value="">{t('experts.googleDrive.chooseAccount')}</option>
                  {activeConnections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name ||
                        c.external_account_name ||
                        t('apps.connections.untitled')}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <p
                className="text-sm text-muted-foreground"
                data-testid="google-drive-single-account"
              >
                {t('experts.googleDrive.connectedAs', {
                  account:
                    activeConnections[0].display_name ||
                    activeConnections[0].external_account_name ||
                    t('apps.connections.untitled'),
                })}
              </p>
            )}
            {selectedConnection ? (
              <div className="flex flex-wrap gap-2">
                <OauthAccountActions
                  connection={selectedConnection}
                  returnPath={`/experts/${expertId}`}
                  compact
                  inline
                />
              </div>
            ) : null}
            {errorKey ? (
              <p className="text-sm text-destructive">{t(errorKey)}</p>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {t('common.cancel')}
          </Button>
          {installed && activeConnections.length > 0 ? (
            <Button
              disabled={!selectedId || busy}
              onClick={() => void handleOpenPicker()}
              data-testid="google-drive-open-picker"
            >
              {busy
                ? t('experts.googleDrive.openingPicker')
                : t('experts.googleDrive.chooseFiles')}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
