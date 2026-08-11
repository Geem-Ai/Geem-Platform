import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  MoreHorizontal,
  Pin,
  PinOff,
  Pencil,
  Trash2,
  MessageSquare,
  Star,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { errorMessageKey } from '@/services/api/errors';
import { ApiError } from '@/services/api/errors';
import type { Conversation } from '@/services/api/types';
import {
  useDeleteConversation,
  useUpdateConversation,
} from '../hooks/useConversationMutations';
import { DeleteConversationDialog } from './DeleteConversationDialog';
import { RenameConversationDialog } from './RenameConversationDialog';

function SectionHeader({ label }: { label: string }) {
  return (
    <p className="text-[0.675rem] font-medium text-muted-foreground uppercase tracking-wide px-2 mb-1.5">
      {label}
    </p>
  );
}

function ConversationRowShimmer() {
  return (
    <div
      className="flex items-center gap-2 rounded-md px-3 py-2"
      data-testid="conversation-row-shimmer"
    >
      <div className="size-3.5 shrink-0 rounded bg-muted animate-pulse" />
      <div className="h-3 w-[65%] rounded bg-muted animate-pulse" />
    </div>
  );
}

function ConversationSectionShimmer({
  title,
  rows = 2,
}: {
  title: string;
  rows?: number;
}) {
  return (
    <div className="px-1.5 mb-3" data-testid="conversation-section-shimmer">
      <SectionHeader label={title} />
      <div className="space-y-0.5">
        {Array.from({ length: rows }, (_, i) => (
          <ConversationRowShimmer key={i} />
        ))}
      </div>
    </div>
  );
}

/** Sidebar loading: Pinned + Recent section headers with row shimmers. */
export function ConversationListsShimmer() {
  const { t } = useTranslation();
  return (
    <div data-testid="conversation-lists-shimmer">
      <ConversationSectionShimmer title={t('chat.pinned')} rows={2} />
      <ConversationSectionShimmer title={t('chat.recent')} rows={3} />
    </div>
  );
}

/** Favorites-only filter loading state. */
export function FavoriteConversationsShimmer() {
  const { t } = useTranslation();
  return (
    <ConversationSectionShimmer title={t('chat.favorites')} rows={3} />
  );
}

function conversationTitle(c: Conversation, untitled: string) {
  return c.title?.trim() || untitled;
}

interface ConversationRowProps {
  conversation: Conversation;
  selected: boolean;
  onOpenChange?: (open: boolean) => void;
}

function ConversationRow({ conversation, selected, onOpenChange }: ConversationRowProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const update = useUpdateConversation();
  const remove = useDeleteConversation();
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const title = conversationTitle(conversation, t('chat.untitled'));
  const isFavorite = Boolean(conversation.is_favorite);

  async function togglePin() {
    try {
      await update.mutateAsync({
        conversationId: conversation.id,
        input: { is_pinned: !conversation.is_pinned },
      });
      toast.success(
        conversation.is_pinned ? t('chat.unpinSuccess') : t('chat.pinSuccess'),
      );
    } catch (err) {
      const key =
        err instanceof ApiError ? errorMessageKey(err.code) : 'errors.generic';
      toast.error(t(key));
    }
  }

  async function toggleFavorite() {
    try {
      await update.mutateAsync({
        conversationId: conversation.id,
        input: { is_favorite: !isFavorite },
      });
      toast.success(
        isFavorite ? t('chat.unfavoriteSuccess') : t('chat.favoriteSuccess'),
      );
    } catch (err) {
      const key =
        err instanceof ApiError ? errorMessageKey(err.code) : 'errors.generic';
      toast.error(t(key));
    }
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync(conversation.id);
      toast.success(t('chat.deleted'));
      setDeleteOpen(false);
      onOpenChange?.(false);
      if (selected) {
        void navigate('/chat');
      }
    } catch (err) {
      const key =
        err instanceof ApiError ? errorMessageKey(err.code) : 'errors.generic';
      toast.error(t(key));
    }
  }

  return (
    <>
      <div
        className={cn(
          'group relative flex items-center rounded-md px-1 py-0.5',
          'has-data-[state=open]:bg-muted',
          selected ? 'bg-primary/10 text-primary' : 'bg-transparent hover:bg-muted',
        )}
        data-testid={`conversation-row-${conversation.id}`}
      >
        <Button
          asChild
          variant="ghost"
          className={cn(
            'flex-1 justify-start gap-2 px-2 h-8 text-xs font-medium truncate',
            selected && 'text-primary hover:text-primary',
          )}
        >
          <Link
            to={`/chat/${conversation.id}`}
            onClick={() => onOpenChange?.(false)}
            title={title}
          >
            <MessageSquare className="size-3.5 shrink-0 text-muted-foreground/60" />
            <span className="truncate">{title}</span>
            {isFavorite && (
              <Star className="size-3 shrink-0 fill-amber-400 text-amber-400 ms-auto" />
            )}
          </Link>
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              mode="icon"
              size="sm"
              className="size-6 opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100 shrink-0"
              aria-label={t('chat.conversationActions')}
              data-testid={`conversation-actions-${conversation.id}`}
            >
              <MoreHorizontal className="size-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={() => void toggleFavorite()}>
              <Star
                className={cn('size-3.5', isFavorite && 'fill-amber-400 text-amber-400')}
              />
              {isFavorite ? t('chat.removeFavorite') : t('chat.addFavorite')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => void togglePin()}>
              {conversation.is_pinned ? (
                <>
                  <PinOff className="size-3.5" />
                  {t('chat.unpin')}
                </>
              ) : (
                <>
                  <Pin className="size-3.5" />
                  {t('chat.pin')}
                </>
              )}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setRenameOpen(true)}>
              <Pencil className="size-3.5" />
              {t('chat.rename')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
            >
              <Trash2 className="size-3.5" />
              {t('chat.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <RenameConversationDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        conversation={conversation}
      />
      <DeleteConversationDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={title}
        onConfirm={() => void confirmDelete()}
        isPending={remove.isPending}
      />
    </>
  );
}

interface ConversationListSectionProps {
  title: string;
  conversations: Conversation[];
  emptyLabel?: string;
  testId: string;
  onOpenChange?: (open: boolean) => void;
}

export function ConversationListSection({
  title,
  conversations,
  emptyLabel,
  testId,
  onOpenChange,
}: ConversationListSectionProps) {
  const { conversationId } = useParams();

  if (conversations.length === 0 && !emptyLabel) {
    return null;
  }

  return (
    <div className="px-1.5 mb-3" data-testid={testId}>
      <SectionHeader label={title} />
      {conversations.length === 0 ? (
        <p className="text-xs text-muted-foreground px-2 py-1">{emptyLabel}</p>
      ) : (
        <div className="space-y-0.5">
          {conversations.map((c) => (
            <ConversationRow
              key={c.id}
              conversation={c}
              selected={conversationId === c.id}
              onOpenChange={onOpenChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function PinnedConversations({
  conversations,
  onOpenChange,
}: {
  conversations: Conversation[];
  onOpenChange?: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const pinned = conversations.filter((c) => c.is_pinned);
  return (
    <ConversationListSection
      title={t('chat.pinned')}
      conversations={pinned}
      emptyLabel={t('chat.noPinned')}
      testId="pinned-conversations"
      onOpenChange={onOpenChange}
    />
  );
}

export function RecentConversations({
  conversations,
  onOpenChange,
}: {
  conversations: Conversation[];
  onOpenChange?: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const recent = conversations.filter((c) => !c.is_pinned);
  return (
    <ConversationListSection
      title={t('chat.recent')}
      conversations={recent}
      emptyLabel={conversations.length === 0 ? t('chat.noConversations') : undefined}
      testId="recent-conversations"
      onOpenChange={onOpenChange}
    />
  );
}

export function FavoriteConversations({
  conversations,
  onOpenChange,
}: {
  conversations: Conversation[];
  onOpenChange?: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const favorites = conversations.filter((c) => c.is_favorite);
  return (
    <ConversationListSection
      title={t('chat.favorites')}
      conversations={favorites}
      emptyLabel={t('chat.noFavorites')}
      testId="favorite-conversations"
      onOpenChange={onOpenChange}
    />
  );
}
