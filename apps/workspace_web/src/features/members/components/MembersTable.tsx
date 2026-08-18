import { useTranslation } from 'react-i18next';
import { formatPeriodDate } from '@/features/usage/lib/quota';
import { RoleBadge } from '@/features/members/components/RoleBadge';
import { MemberRowActions } from '@/features/members/components/MemberRowActions';
import type { Member } from '@/services/api/types';

type MembersTableProps = {
  members: Member[];
  currentUserId: string | undefined;
  actorRole: string | null | undefined;
  canManage: boolean;
  busy?: boolean;
  onChangeRole: (userId: string, role: 'owner' | 'admin' | 'member') => void;
  onRemove: (member: Member) => void;
};

function initials(email: string | null, userId: string): string {
  const source = (email ?? userId).trim();
  return (source[0] ?? '?').toUpperCase();
}

export function MembersTable({
  members,
  currentUserId,
  actorRole,
  canManage,
  busy,
  onChangeRole,
  onRemove,
}: MembersTableProps) {
  const { t, i18n } = useTranslation();

  if (members.length === 0) {
    return (
      <p className="text-sm text-muted-foreground px-5 py-8" data-testid="members-empty">
        {t('members.emptyMembers')}
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border" data-testid="members-table">
      {members.map((member) => {
        const isSelf = member.user_id === currentUserId;
        const joined = formatPeriodDate(member.created_at, i18n.language);
        return (
          <li
            key={member.id}
            className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
            data-testid="member-row"
          >
            <div className="flex min-w-0 items-center gap-3">
              <span
                className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary"
                aria-hidden
              >
                {initials(member.email, member.user_id)}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {member.email ?? member.user_id}
                  {isSelf ? (
                    <span className="ms-1.5 text-xs font-normal text-muted-foreground">
                      ({t('members.you')})
                    </span>
                  ) : null}
                </p>
                <p className="text-xs text-muted-foreground">
                  {joined
                    ? t('members.joinedOn', { date: joined })
                    : t(`roles.${member.role}`)}
                </p>
              </div>
            </div>
            <div className="flex items-center justify-between gap-3 sm:justify-end">
              <RoleBadge role={member.role} />
              {canManage ? (
                <MemberRowActions
                  actorRole={actorRole}
                  memberRole={member.role}
                  disabled={busy}
                  onChangeRole={(role) => onChangeRole(member.user_id, role)}
                  onRemove={() => onRemove(member)}
                />
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
