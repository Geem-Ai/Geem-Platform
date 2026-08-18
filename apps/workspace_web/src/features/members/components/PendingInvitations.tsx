import { useTranslation } from 'react-i18next';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatPeriodDateTime } from '@/features/usage/lib/quota';
import { RoleBadge } from '@/features/members/components/RoleBadge';
import type { WorkspaceInvitationSummary } from '@/services/api/invitations';

type PendingInvitationsProps = {
  invitations: WorkspaceInvitationSummary[];
  busyId?: string | null;
  onResend: (invitation: WorkspaceInvitationSummary) => void;
  onRevoke: (invitation: WorkspaceInvitationSummary) => void;
};

export function PendingInvitations({
  invitations,
  busyId,
  onResend,
  onRevoke,
}: PendingInvitationsProps) {
  const { t, i18n } = useTranslation();

  if (invitations.length === 0) {
    return (
      <div className="px-5 py-8 space-y-1" data-testid="invitations-empty">
        <p className="text-sm text-muted-foreground">{t('members.emptyInvites')}</p>
        <p className="text-xs text-muted-foreground">{t('members.emptyInvitesHint')}</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border" data-testid="pending-invitations">
      {invitations.map((invite) => {
        const busy = busyId === invite.id;
        const expires = formatPeriodDateTime(invite.expires_at, i18n.language);
        const inviter = invite.invited_by?.email;
        return (
          <li
            key={invite.id}
            className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
            data-testid="invitation-row"
          >
            <div className="min-w-0 space-y-1">
              <p className="truncate text-sm font-medium">{invite.email}</p>
              <p className="text-xs text-muted-foreground">
                {inviter
                  ? t('members.invitedBy', { email: inviter })
                  : t('members.pending')}
                {expires ? ` · ${t('members.expiresOn', { date: expires })}` : ''}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <RoleBadge role={invite.role} />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => onResend(invite)}
                data-testid="resend-invitation"
              >
                {busy ? <LoaderCircle className="size-3.5 animate-spin" aria-hidden /> : null}
                {t('members.resend')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => onRevoke(invite)}
                data-testid="revoke-invitation"
              >
                {t('members.revoke')}
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
