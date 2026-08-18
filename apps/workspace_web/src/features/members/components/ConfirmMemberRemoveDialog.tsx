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
import type { Member } from '@/services/api/types';

type ConfirmMemberRemoveDialogProps = {
  member: Member | null;
  pending?: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
};

export function ConfirmMemberRemoveDialog({
  member,
  pending,
  onOpenChange,
  onConfirm,
}: ConfirmMemberRemoveDialogProps) {
  const { t } = useTranslation();
  const name = member?.email ?? member?.user_id ?? '';

  return (
    <AlertDialog open={Boolean(member)} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="remove-member-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('members.removeTitle', { name })}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('members.removeDescription', { name })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={pending}
            onClick={onConfirm}
            data-testid="confirm-remove-member"
          >
            {t('members.remove')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
