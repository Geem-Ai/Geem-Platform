import { useTranslation } from 'react-i18next';
import { LoaderCircle, MailPlus, UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatPeriodDateTime } from '@/features/usage/lib/quota';
import { RoleBadge } from '@/features/members/components/RoleBadge';
import type { WorkspaceInvitationSummary } from '@/services/api/invitations';

type PendingInvitationsProps = {
  invitations: WorkspaceInvitationSummary[];
  busyId?: string | null;
  onInvite?: () => void;
  onResend: (invitation: WorkspaceInvitationSummary) => void;
  onRevoke: (invitation: WorkspaceInvitationSummary) => void;
};

export function PendingInvitations({
  invitations,
  busyId,
  onInvite,
  onResend,
  onRevoke,
}: PendingInvitationsProps) {
  const { t, i18n } = useTranslation();

  if (invitations.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center"
        data-testid="invitations-empty"
      >
        <div
          className="flex size-11 items-center justify-center rounded-xl bg-muted text-muted-foreground"
          aria-hidden
        >
          <MailPlus className="size-5" />
        </div>
        <div className="space-y-1 max-w-sm">
          <p className="text-sm font-medium">{t('members.emptyInvites')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t('members.emptyInvitesHint')}
          </p>
        </div>
        {onInvite ? (
          <Button
            type="button"
            size="sm"
            onClick={onInvite}
            data-testid="invitations-empty-invite"
          >
            <UserPlus className="size-3.5" />
            {t('members.invite')}
          </Button>
        ) : null}
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
