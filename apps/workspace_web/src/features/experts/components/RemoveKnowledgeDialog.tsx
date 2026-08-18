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
  const filename = item?.title || item?.original_filename || '';

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!isPending) onOpenChange(next);
      }}
    >
      <AlertDialogContent data-testid="remove-knowledge-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('experts.removeTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('experts.removeHint')}</AlertDialogDescription>
        </AlertDialogHeader>
        {item ? (
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm font-medium break-all">
            {filename}
          </div>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={isPending || !item}
            onClick={(event) => {
              event.preventDefault();
              if (item) onConfirm(item);
            }}
            data-testid="remove-knowledge-confirm"
          >
            {t('experts.confirmRemove')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
