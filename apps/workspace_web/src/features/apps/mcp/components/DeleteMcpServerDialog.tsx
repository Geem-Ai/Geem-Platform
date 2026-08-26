import {
  AlertTriangle,
  KeyRound,
  Server,
  ShieldOff,
  Trash2,
  Wrench,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { McpServer } from '@/services/api/mcp';

type DeleteMcpServerDialogProps = {
  server: McpServer | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (server: McpServer) => void;
  isPending?: boolean;
  errorMessage?: string | null;
};

function serverName(server: McpServer): string {
  return server.display_name || server.endpoint_host || server.id;
}

export function DeleteMcpServerDialog({
  server,
  open,
  onOpenChange,
  onConfirm,
  isPending,
  errorMessage,
}: DeleteMcpServerDialogProps) {
  const { t } = useTranslation();
  const effects = [
    { icon: KeyRound, text: t('apps.mcp.deleteEffectCredentials') },
    { icon: ShieldOff, text: t('apps.mcp.deleteEffectGrants') },
    { icon: Wrench, text: t('apps.mcp.deleteEffectTools') },
  ] as const;

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!isPending) onOpenChange(next);
      }}
    >
      <AlertDialogContent className="sm:max-w-md" data-testid="mcp-delete-dialog">
        <AlertDialogHeader>
          <div className="mx-auto mb-1 flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive sm:mx-0">
            <Trash2 className="size-5" aria-hidden />
          </div>
          <AlertDialogTitle>{t('apps.mcp.deleteTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('apps.mcp.deleteHint', {
              name: server ? serverName(server) : '',
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {server ? (
          <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 p-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-background text-muted-foreground shadow-xs">
              <Server className="size-4" aria-hidden />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium" dir="auto">
                {serverName(server)}
              </p>
              {server.endpoint_host ? (
                <p className="truncate text-xs text-muted-foreground" dir="ltr">
                  {server.endpoint_host}
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        <div
          role="note"
          className="space-y-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3"
        >
          <div className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-4 shrink-0" aria-hidden />
            <p className="text-sm font-medium">{t('apps.mcp.deleteImpactTitle')}</p>
          </div>
          <ul className="space-y-2">
            {effects.map(({ icon: Icon, text }) => (
              <li
                key={text}
                className="flex items-start gap-2 text-xs text-muted-foreground"
              >
                <Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </div>

        {errorMessage ? (
          <p
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          >
            {errorMessage}
          </p>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending} data-testid="mcp-delete-cancel">
            {t('common.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={isPending || !server}
            onClick={(event) => {
              event.preventDefault();
              if (server) onConfirm(server);
            }}
            data-testid="mcp-delete-confirm"
          >
            <Trash2 className="size-4" aria-hidden />
            {isPending ? t('apps.mcp.deletingServer') : t('apps.mcp.deleteServer')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
