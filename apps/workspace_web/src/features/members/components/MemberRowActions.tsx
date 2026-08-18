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
import { isOwnerRole } from '@/features/authz/role-summary';
import type { RoleSummary } from '@/services/api/types';

type MemberRowActionsProps = {
  memberRole: RoleSummary;
  assignableRoles: RoleSummary[];
  canChangeRole: boolean;
  canRemove: boolean;
  canAssignOwner: boolean;
  ownerRole?: RoleSummary | null;
  disabled?: boolean;
  onChangeRole: (roleId: string) => void;
  onRemove: () => void;
};

export function MemberRowActions({
  memberRole,
  assignableRoles,
  canChangeRole,
  canRemove,
  canAssignOwner,
  ownerRole,
  disabled,
  onChangeRole,
  onRemove,
}: MemberRowActionsProps) {
  const { t } = useTranslation();
  const options = [...assignableRoles];
  if (canAssignOwner && ownerRole && !options.some((row) => row.id === ownerRole.id)) {
    options.unshift(ownerRole);
  }

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
        {canChangeRole
          ? options
              .filter((row) => row.id !== memberRole.id)
              .map((row) => (
                <DropdownMenuItem
                  key={row.id}
                  onSelect={() => onChangeRole(row.id)}
                  data-testid={`assign-role-${row.id}`}
                >
                  {t('members.makeRole', { role: row.name })}
                </DropdownMenuItem>
              ))
          : null}
        {canChangeRole && canRemove ? <DropdownMenuSeparator /> : null}
        {canRemove && !isOwnerRole(memberRole) ? (
          <DropdownMenuItem
            variant="destructive"
            onSelect={onRemove}
            data-testid="remove-member"
          >
            {t('members.remove')}
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
