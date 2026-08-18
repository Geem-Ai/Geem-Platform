import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { ExpertKnowledgeItem } from '@/services/api/types';
import { useRenameExpertDocument } from '../hooks/useExpertMutations';

interface RenameKnowledgeDialogProps {
  expertId: string;
  item: ExpertKnowledgeItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RenameKnowledgeDialog({
  expertId,
  item,
  open,
  onOpenChange,
}: RenameKnowledgeDialogProps) {
  const { t } = useTranslation();
  const rename = useRenameExpertDocument(expertId);
  const initial = (item?.title || item?.original_filename || '').trim();
  const [title, setTitle] = useState(initial);

  useEffect(() => {
    if (open) setTitle((item?.title || item?.original_filename || '').trim());
  }, [open, item?.title, item?.original_filename]);

  const trimmed = title.trim();
  const canSave = Boolean(item?.document_id) && trimmed.length > 0 && trimmed !== initial;

  async function handleSave() {
    if (!item?.document_id || !canSave) return;
    try {
      await rename.mutateAsync({ documentId: item.document_id, title: trimmed });
      toast.success(t('experts.renamed'));
      onOpenChange(false);
    } catch (err) {
      const key =
        err instanceof ApiError ? errorMessageKey(err.code) : 'errors.generic';
      toast.error(t(key));
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!rename.isPending) onOpenChange(next); }}>
      <DialogContent className="sm:max-w-md" data-testid="rename-knowledge-dialog">
        <DialogHeader>
          <DialogTitle>{t('experts.renameTitle')}</DialogTitle>
          <DialogDescription>{t('experts.renameHint')}</DialogDescription>
        </DialogHeader>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={512}
          placeholder={t('experts.renamePlaceholder')}
          autoFocus
          disabled={rename.isPending}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void handleSave();
            }
          }}
        />
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={rename.isPending}
          >
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={rename.isPending || !canSave}
            data-testid="rename-knowledge-save"
          >
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
