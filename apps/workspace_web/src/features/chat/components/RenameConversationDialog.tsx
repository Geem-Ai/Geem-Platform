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
import type { Conversation } from '@/services/api/types';
import { useUpdateConversation } from '../hooks/useConversationMutations';

interface RenameConversationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversation: Conversation;
}

export function RenameConversationDialog({
  open,
  onOpenChange,
  conversation,
}: RenameConversationDialogProps) {
  const { t } = useTranslation();
  const update = useUpdateConversation();
  const [title, setTitle] = useState(conversation.title ?? '');

  useEffect(() => {
    if (open) setTitle(conversation.title ?? '');
  }, [open, conversation.title]);

  async function handleSave() {
    const next = title.trim();
    try {
      await update.mutateAsync({
        conversationId: conversation.id,
        input: { title: next || null },
      });
      toast.success(t('chat.renamed'));
      onOpenChange(false);
    } catch (err) {
      const key =
        err instanceof ApiError ? errorMessageKey(err.code) : 'errors.generic';
      toast.error(t(key));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="rename-conversation-dialog">
        <DialogHeader>
          <DialogTitle>{t('chat.renameTitle')}</DialogTitle>
          <DialogDescription>{t('chat.renameDescription')}</DialogDescription>
        </DialogHeader>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          placeholder={t('chat.renamePlaceholder')}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void handleSave();
            }
          }}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('chat.cancel')}
          </Button>
          <Button onClick={() => void handleSave()} disabled={update.isPending}>
            {t('chat.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
