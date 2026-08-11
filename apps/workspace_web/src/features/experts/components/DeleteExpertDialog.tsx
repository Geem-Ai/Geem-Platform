import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { Expert } from '@/services/api/types';

interface DeleteExpertDialogProps {
  expert: Expert;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  isPending?: boolean;
}

export function DeleteExpertDialog({
  expert,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: DeleteExpertDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!isPending) onOpenChange(o); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('experts.deleteTitle')}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          <strong>{expert.name}</strong> — {t('experts.deleteHint')}
        </p>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? t('experts.deleting') : t('experts.deleteConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
