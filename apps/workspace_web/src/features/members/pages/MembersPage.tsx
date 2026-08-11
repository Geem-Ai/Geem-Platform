import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/features/auth/AuthProvider';
import {
  canChangeMemberRoles,
  canManageMembers,
  canPromoteToOwner,
} from '@/features/workspaces/lib/roles';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { listMembers, removeMember, updateMemberRole } from '@/services/api';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';

export function MembersPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { currentWorkspace, currentMembership } = useWorkspace();
  const queryClient = useQueryClient();
  const workspaceId = currentWorkspace?.id ?? '';
  const role = currentMembership?.role ?? currentWorkspace?.role;

  const membersQuery = useQuery({
    queryKey: queryKeys.members(workspaceId),
    queryFn: () => listMembers(workspaceId),
    enabled: Boolean(workspaceId),
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, nextRole }: { userId: string; nextRole: 'owner' | 'admin' | 'member' }) =>
      updateMemberRole(workspaceId, userId, nextRole),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
      toast.success(t('members.roleUpdated'));
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
      } else {
        toast.error(t('errors.generic'));
      }
    },
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => removeMember(workspaceId, userId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
      toast.success(t('members.removed'));
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
      } else {
        toast.error(t('errors.generic'));
      }
    },
  });

  const canManage = canManageMembers(role);

  return (
    <div className="p-6 md:p-8 w-full max-w-3xl space-y-6 ms-auto me-auto">
      <Helmet>
        <title>
          {t('members.title')} · {t('app.name')}
        </title>
      </Helmet>
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('members.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('members.description')}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('members.listTitle')}</CardTitle>
          <CardDescription>{t('members.noInviteHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {membersQuery.isLoading && (
            <p className="text-sm text-muted-foreground">{t('shell.loading')}</p>
          )}
          {membersQuery.isError && (
            <p className="text-sm text-destructive">{t('errors.generic')}</p>
          )}
          {membersQuery.data?.map((member) => {
            const isSelf = member.user_id === user?.id;
            return (
              <div
                key={member.id}
                className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between border-b border-border last:border-0 pb-3 last:pb-0"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {member.email ?? member.user_id}
                    {isSelf ? ` (${t('members.you')})` : ''}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t(`roles.${member.role}`)}
                  </p>
                </div>
                {canManage && (
                  <div className="flex flex-wrap items-center gap-2">
                    {canChangeMemberRoles(role) && (
                      <select
                        className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                        value={member.role}
                        disabled={roleMutation.isPending}
                        onChange={(e) => {
                          const nextRole = e.target.value as 'owner' | 'admin' | 'member';
                          if (nextRole === 'owner' && !canPromoteToOwner(role)) {
                            toast.error(t('errors.insufficientRole'));
                            return;
                          }
                          roleMutation.mutate({ userId: member.user_id, nextRole });
                        }}
                      >
                        <option value="member">{t('roles.member')}</option>
                        <option value="admin">{t('roles.admin')}</option>
                        {canPromoteToOwner(role) && (
                          <option value="owner">{t('roles.owner')}</option>
                        )}
                      </select>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={removeMutation.isPending}
                      onClick={() => {
                        if (window.confirm(t('members.confirmRemove'))) {
                          removeMutation.mutate(member.user_id);
                        }
                      }}
                    >
                      {t('members.remove')}
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
