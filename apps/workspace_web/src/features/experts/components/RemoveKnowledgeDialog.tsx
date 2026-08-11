import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { ExpertKnowledgeItem } from '@/services/api/types';

interface RemoveKnowledgeDialogProps {
  item: ExpertKnowledgeItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (item: ExpertKnowledgeItem) => void;
  isPending?: boolean;
}

export function RemoveKnowledgeDialog({
  item,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: RemoveKnowledgeDialogProps) {
  const { t } = useTranslation();

  if (!item) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!isPending) onOpenChange(o); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('experts.removeTitle')}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          <strong>{item.title || item.original_filename}</strong>
        </p>
        <p className="text-sm text-muted-foreground">{t('experts.removeHint')}</p>
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
            onClick={() => onConfirm(item)}
            disabled={isPending}
          >
            {t('experts.confirmRemove')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
