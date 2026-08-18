import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { MoreHorizontal } from 'lucide-react';
import {
  canChangeMemberRoles,
  canPromoteToOwner,
} from '@/features/workspaces/lib/roles';

type MemberRowActionsProps = {
  actorRole: string | null | undefined;
  memberRole: string;
  disabled?: boolean;
  onChangeRole: (role: 'owner' | 'admin' | 'member') => void;
  onRemove: () => void;
};

export function MemberRowActions({
  actorRole,
  memberRole,
  disabled,
  onChangeRole,
  onRemove,
}: MemberRowActionsProps) {
  const { t } = useTranslation();
  const canRoles = canChangeMemberRoles(actorRole);
  const canOwner = canPromoteToOwner(actorRole);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          aria-label={t('members.memberActions')}
          data-testid="member-row-actions"
        >
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        {canRoles ? (
          <>
            {memberRole !== 'member' ? (
              <DropdownMenuItem onSelect={() => onChangeRole('member')}>
                {t('members.makeRole', { role: t('roles.member') })}
              </DropdownMenuItem>
            ) : null}
            {memberRole !== 'admin' ? (
              <DropdownMenuItem onSelect={() => onChangeRole('admin')}>
                {t('members.makeRole', { role: t('roles.admin') })}
              </DropdownMenuItem>
            ) : null}
            {canOwner && memberRole !== 'owner' ? (
              <DropdownMenuItem onSelect={() => onChangeRole('owner')}>
                {t('members.makeRole', { role: t('roles.owner') })}
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuSeparator />
          </>
        ) : null}
        <DropdownMenuItem variant="destructive" onSelect={onRemove}>
          {t('members.remove')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
