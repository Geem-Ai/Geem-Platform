import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FileText, Star, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useLayout } from '@/app/layouts/workspace/context';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { useConversations } from '../hooks/useConversations';
import { useClearConversationHistory } from '../hooks/useConversationMutations';

function SectionHeader({ label }: { label: string }) {
  return (
    <p className="text-[0.675rem] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
      {label}
    </p>
  );
}

interface QuickActionsProps {
  collapsed?: boolean;
}

export function QuickActions({ collapsed = false }: QuickActionsProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { conversationId } = useParams();
  const { showFavoritesOnly, setShowFavoritesOnly } = useLayout();
  const conversationsQuery = useConversations();
  const conversations = conversationsQuery.data ?? [];
  const clearHistory = useClearConversationHistory();
  const [clearOpen, setClearOpen] = useState(false);
  const tooltipSide = i18n.language === 'ar' ? 'left' : 'right';
  const favoriteCount = conversations.filter((c) => c.is_favorite).length;
  const hasHistory = conversations.length > 0;
  const clearing = clearHistory.isPending;

  async function confirmClearHistory() {
    if (clearing) return;
    try {
      const result = await clearHistory.mutateAsync();
      toast.success(
        t('chat.clearHistorySuccess', { count: result.deleted_count }),
      );
      setClearOpen(false);
      setShowFavoritesOnly(false);
      if (conversationId) {
        void navigate('/chat', { replace: true });
      }
    } catch (err) {
      const key =
        err instanceof ApiError ? errorMessageKey(err.code) : 'errors.generic';
      toast.error(t(key));
    }
  }

  if (collapsed) {
    return (
      <div className="space-y-2 flex flex-col items-center" data-testid="quick-actions">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              mode="icon"
              variant={showFavoritesOnly ? 'secondary' : 'ghost'}
              onClick={() => setShowFavoritesOnly((v) => !v)}
              aria-label={t('chat.favorites')}
            >
              <Star className={cn('size-4', showFavoritesOnly && 'fill-current')} />
            </Button>
          </TooltipTrigger>
          <TooltipContent side={tooltipSide}>{t('chat.favorites')}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              mode="icon"
              variant="ghost"
              onClick={() => setClearOpen(true)}
              disabled={!hasHistory}
              aria-label={t('chat.clearHistory')}
            >
              <Trash2 className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side={tooltipSide}>{t('chat.clearHistory')}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              mode="icon"
              variant="ghost"
              onClick={(e) => e.preventDefault()}
              aria-label={t('chat.templates')}
            >
              <FileText className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side={tooltipSide}>{t('chat.soon')}</TooltipContent>
        </Tooltip>

        <ClearHistoryDialog
          open={clearOpen}
          onOpenChange={setClearOpen}
          onConfirm={() => void confirmClearHistory()}
          isPending={clearing}
          disabled={!hasHistory}
        />
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="quick-actions">
      <SectionHeader label={t('chat.quickActions')} />
      <div className="space-y-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(
            'w-full justify-start gap-2 text-muted-foreground hover:text-foreground',
            showFavoritesOnly && 'bg-accent text-accent-foreground',
          )}
          onClick={() => setShowFavoritesOnly((v) => !v)}
        >
          <Star className={cn('size-4', showFavoritesOnly && 'fill-current')} />
          <span className="text-sm">{t('chat.favorites')}</span>
          {favoriteCount > 0 && (
            <Badge variant="info" appearance="outline" size="sm" className="ms-auto">
              {favoriteCount}
            </Badge>
          )}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
          onClick={() => setClearOpen(true)}
          disabled={!hasHistory}
        >
          <Trash2 className="size-4" />
          <span className="text-sm">{t('chat.clearHistory')}</span>
        </Button>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
              onClick={(e) => e.preventDefault()}
            >
              <FileText className="size-4" />
              <span className="text-sm">{t('chat.templates')}</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top">{t('chat.soon')}</TooltipContent>
        </Tooltip>
      </div>

      <ClearHistoryDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        onConfirm={() => void confirmClearHistory()}
        isPending={clearing}
        disabled={!hasHistory}
      />
    </div>
  );
}

function ClearHistoryDialog({
  open,
  onOpenChange,
  onConfirm,
  isPending,
  disabled,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  isPending: boolean;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('chat.clearHistoryTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('chat.clearHistoryDescription')}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>{t('chat.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={isPending || disabled}
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
          >
            {isPending ? t('chat.clearingHistory') : t('chat.clearHistory')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
