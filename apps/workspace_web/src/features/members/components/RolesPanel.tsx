import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RoleEditorDialog } from '@/features/members/components/RoleEditorDialog';
import {
  useCreateRole,
  useDeleteRole,
  usePermissionCatalog,
  useUpdateRole,
  useWorkspaceRoles,
} from '@/features/members/hooks/useMembersQueries';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { WorkspaceRoleDetail } from '@/services/api/roles';

type RolesPanelProps = {
  canManage: boolean;
};

export function RolesPanel({ canManage }: RolesPanelProps) {
  const { t } = useTranslation();
  const rolesQuery = useWorkspaceRoles();
  const catalogQuery = usePermissionCatalog({ enabled: canManage });
  const createRole = useCreateRole();
  const updateRole = useUpdateRole();
  const deleteRole = useDeleteRole();
  const [editor, setEditor] = useState<WorkspaceRoleDetail | 'new' | null>(null);

  const roles = rolesQuery.data?.items ?? [];
  const catalog = catalogQuery.data?.items ?? [];

  function handleSave(input: {
    name: string;
    description: string | null;
    permissions: string[];
  }) {
    if (editor === 'new') {
      createRole.mutate(input, {
        onSuccess: () => {
          toast.success(t('members.roles.created'));
          setEditor(null);
        },
        onError: (err: unknown) => {
          if (err instanceof ApiError) toast.error(t(errorMessageKey(err.code)));
          else toast.error(t('errors.generic'));
        },
      });
      return;
    }
    if (!editor) return;
    updateRole.mutate(
      { roleId: editor.id, ...input },
      {
        onSuccess: () => {
          toast.success(t('members.roles.updated'));
          setEditor(null);
        },
        onError: (err: unknown) => {
          if (err instanceof ApiError) toast.error(t(errorMessageKey(err.code)));
          else toast.error(t('errors.generic'));
        },
      },
    );
  }

  function handleDelete(role: WorkspaceRoleDetail) {
    if (!window.confirm(t('members.roles.deleteConfirm', { name: role.name }))) return;
    deleteRole.mutate(role.id, {
      onSuccess: () => toast.success(t('members.roles.deleted')),
      onError: (err: unknown) => {
        if (err instanceof ApiError) toast.error(t(errorMessageKey(err.code)));
        else toast.error(t('errors.generic'));
      },
    });
  }

  return (
    <div className="space-y-4" data-testid="roles-panel">
      <div className="flex items-center justify-between gap-3 px-5 pt-1">
        <p className="text-sm text-muted-foreground">{t('members.roles.listHint')}</p>
        {canManage ? (
          <Button
            type="button"
            size="sm"
            onClick={() => setEditor('new')}
            data-testid="create-role-button"
          >
            <Plus className="size-3.5" />
            {t('members.roles.create')}
          </Button>
        ) : null}
      </div>
      {rolesQuery.isLoading ? (
        <div className="space-y-3 p-5" data-testid="roles-loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 rounded bg-muted animate-pulse" />
          ))}
        </div>
      ) : null}
      {rolesQuery.isError ? (
        <p className="text-sm text-destructive px-5 py-6">{t('errors.generic')}</p>
      ) : null}
      <ul className="divide-y divide-border">
        {roles.map((role) => (
          <li
            key={role.id}
            className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
            data-testid="role-row"
          >
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium">{role.name}</p>
                {role.is_owner_role ? (
                  <Badge variant="primary" appearance="light" size="sm">
                    {t('members.roles.systemOwner')}
                  </Badge>
                ) : role.is_system ? (
                  <Badge variant="info" appearance="light" size="sm">
                    {t('members.roles.system')}
                  </Badge>
                ) : (
                  <Badge variant="secondary" appearance="light" size="sm">
                    {t('members.roles.custom')}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {role.is_owner_role
                  ? t('members.roles.ownerFullAccess')
                  : t('members.roles.assignedCount', { count: role.assigned_count })}
              </p>
            </div>
            {canManage ? (
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setEditor(role)}
                  data-testid={`edit-role-${role.id}`}
                >
                  {role.is_owner_role ? t('members.roles.view') : t('members.roles.edit')}
                </Button>
                {!role.is_system ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(role)}
                    data-testid="delete-role"
                  >
                    {t('common.delete')}
                  </Button>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      <RoleEditorDialog
        open={editor !== null}
        onOpenChange={(open) => {
          if (!open) setEditor(null);
        }}
        catalog={catalog}
        role={editor && editor !== 'new' ? editor : null}
        pending={createRole.isPending || updateRole.isPending}
        onSave={handleSave}
      />
    </div>
  );
}
