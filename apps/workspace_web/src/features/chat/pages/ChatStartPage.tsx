import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/features/auth/AuthProvider';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { canAskExpert } from '@/features/experts/lib/capabilities';
import { useExperts } from '@/features/experts/hooks/useExperts';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { Expert } from '@/services/api/types';
import { ChatStarter } from '../components/ChatStarter';
import { useCreateConversation } from '../hooks/useConversationMutations';

export type ChatPendingLocationState = {
  pendingMessage?: string;
};

export function ChatStartPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const createConversation = useCreateConversation();

  const expertsQuery = useExperts();
  const allExperts: Expert[] = useMemo(
    () => expertsQuery.data ?? [],
    [expertsQuery.data],
  );

  const expertIdParam = searchParams.get('expert');
  const [selectedExpertId, setSelectedExpertId] = useState<string | null>(expertIdParam);
  const [invalidDeepLink, setInvalidDeepLink] = useState(false);

  useEffect(() => {
    setSelectedExpertId(expertIdParam);
    setInvalidDeepLink(false);
  }, [expertIdParam, workspaceId]);

  useEffect(() => {
    if (expertsQuery.isLoading || !workspaceId) return;

    if (selectedExpertId) {
      const found = allExperts.some((e) => e.id === selectedExpertId);
      if (!found) {
        setInvalidDeepLink(Boolean(expertIdParam));
        setSelectedExpertId(null);
        if (expertIdParam) {
          setSearchParams({}, { replace: true });
        }
      }
      return;
    }

    // New chat always defaults to Geem General unless `?expert=` deep-link is present.
    if (expertIdParam) return;
    const geemGeneral = allExperts.find(
      (e) => e.ownership === 'platform' && e.knowledge_mode === 'general' && canAskExpert(e.status),
    );
    if (geemGeneral) {
      setSelectedExpertId(geemGeneral.id);
      setSearchParams({ expert: geemGeneral.id }, { replace: true });
    }
  }, [
    allExperts,
    expertIdParam,
    expertsQuery.isLoading,
    selectedExpertId,
    setSearchParams,
    workspaceId,
  ]);

  function handleSelectExpert(id: string) {
    setInvalidDeepLink(false);
    setSelectedExpertId(id);
    setSearchParams({ expert: id }, { replace: true });
  }

  const selectedExpert = selectedExpertId
    ? allExperts.find((e) => e.id === selectedExpertId) ?? null
    : null;

  const askEnabled = selectedExpert ? canAskExpert(selectedExpert.status) : false;

  let askHint: string | null = null;
  if (selectedExpert && !askEnabled) {
    if (selectedExpert.status === 'draft') askHint = t('chat.askDisabledDraft');
    else if (selectedExpert.status === 'processing')
      askHint = t('chat.askDisabledProcessing');
    else if (selectedExpert.status === 'failed') askHint = t('chat.askDisabledFailed');
    else askHint = t('chat.askDisabled');
  }

  async function handleSubmit(content: string) {
    if (!selectedExpert || !askEnabled || createConversation.isPending) return;
    try {
      const conversation = await createConversation.mutateAsync({
        expert_id: selectedExpert.id,
      });
      void navigate(`/chat/${conversation.id}`, {
        state: { pendingMessage: content } satisfies ChatPendingLocationState,
      });
    } catch (err) {
      const key =
        err instanceof ApiError ? errorMessageKey(err.code) : 'errors.generic';
      toast.error(t(key));
    }
  }

  return (
    <div
      className="flex flex-col h-[calc(100vh-var(--header-height-mobile)-3.5rem)] lg:h-[calc(100vh-2.5rem)]"
      data-testid="chat-start-page"
    >
      <Helmet>
        <title>
          {t('chat.title')} — {t('app.name')}
        </title>
      </Helmet>

      <ChatStarter
        experts={allExperts}
        selectedExpertId={selectedExpertId}
        onSelectExpert={handleSelectExpert}
        onSubmit={(c) => void handleSubmit(c)}
        expertsLoading={expertsQuery.isLoading}
        submitting={createConversation.isPending}
        disabled={!askEnabled}
        askHint={askHint}
        invalidDeepLink={invalidDeepLink}
      />
    </div>
  );
}

/** Initials helper shared with ChatPage. */
export function userInitialsFromEmail(email: string | undefined | null): string {
  if (!email) return 'U';
  const local = email.split('@')[0] || email;
  return local.slice(0, 2).toUpperCase();
}

export function useCurrentUserInitials(): string {
  const { user } = useAuth();
  return userInitialsFromEmail(user?.email);
}
