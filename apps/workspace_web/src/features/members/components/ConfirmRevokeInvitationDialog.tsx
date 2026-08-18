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
import type { WorkspaceInvitationSummary } from '@/services/api/invitations';

type ConfirmRevokeInvitationDialogProps = {
  invitation: WorkspaceInvitationSummary | null;
  pending?: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
};

export function ConfirmRevokeInvitationDialog({
  invitation,
  pending,
  onOpenChange,
  onConfirm,
}: ConfirmRevokeInvitationDialogProps) {
  const { t } = useTranslation();
  const email = invitation?.email ?? '';

  return (
    <AlertDialog open={Boolean(invitation)} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="revoke-invitation-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('members.revokeTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('members.revokeDescription', { email })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={pending}
            onClick={onConfirm}
            data-testid="confirm-revoke-invitation"
          >
            {t('members.revoke')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
