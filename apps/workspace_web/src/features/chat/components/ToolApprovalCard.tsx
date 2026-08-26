import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { decideConversationToolApproval } from '@/services/api/mcp';
import { queryKeys } from '@/services/api/query-keys';
import type { ChatToolApproval } from '@/services/api/types';

function exactArguments(value: ChatToolApproval['arguments']): string {
  try { return JSON.stringify(value ?? {}, null, 2); } catch { return '{}'; }
}

export function ToolApprovalCard({ approval }: { approval: ChatToolApproval }) {
  const { t } = useTranslation();
  const { conversationId = '' } = useParams<{ conversationId: string }>();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<'approve' | 'deny' | null>(null);
  const actionable = approval.status === 'pending';

  async function decide(decision: 'approve' | 'deny') {
    if (!conversationId || !actionable) return;
    setPending(decision);
    try {
      await decideConversationToolApproval(conversationId, approval.id, decision);
      toast.success(t(decision === 'approve' ? 'chat.tools.approved' : 'chat.tools.denied'));
      const key = queryKeys.conversationMessages(workspaceId, conversationId);
      await queryClient.invalidateQueries({ queryKey: key });
      if (decision === 'approve') {
        window.setTimeout(() => void queryClient.invalidateQueries({ queryKey: key }), 1_500);
        window.setTimeout(() => void queryClient.invalidateQueries({ queryKey: key }), 4_000);
      }
    } catch (error) {
      toast.error(t(errorMessageKey(error instanceof ApiError ? error.code : 'unknown')));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mt-3 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 space-y-3" data-testid="tool-approval-card" data-status={approval.status}>
      <div className="flex items-start gap-2"><ShieldAlert className="size-4 mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden /><div><p className="text-sm font-semibold">{t('chat.tools.approvalRequired')}</p><p className="text-xs text-muted-foreground" dir="auto">{approval.connection_name ? `${approval.connection_name} · ` : ''}{approval.tool_name}</p></div></div>
      <div><p className="text-xs font-medium mb-1">{t('chat.tools.exactArguments')}</p><pre className="max-h-52 overflow-auto rounded-lg border border-border bg-background p-2.5 text-xs whitespace-pre-wrap break-all" dir="ltr" data-testid="tool-approval-arguments">{exactArguments(approval.arguments)}</pre></div>
      <p className="text-xs text-muted-foreground">{t('chat.tools.approvalDisclosure')}</p>
      {actionable ? <div className="flex gap-2"><Button type="button" size="sm" onClick={() => void decide('approve')} disabled={pending !== null}>{t('chat.tools.approveOnce')}</Button><Button type="button" size="sm" variant="destructive" onClick={() => void decide('deny')} disabled={pending !== null}>{t('chat.tools.deny')}</Button></div> : <p className="text-xs font-medium">{t(`chat.tools.approvalStatus.${approval.status}`, { defaultValue: approval.status })}</p>}
    </div>
  );
}
