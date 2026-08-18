import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { UserPlus } from 'lucide-react';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/features/auth/AuthProvider';
import { WorkspacePermission } from '@/features/authz/permissions';
import { usePermissions } from '@/features/authz/usePermissions';
import { ConfirmMemberRemoveDialog } from '@/features/members/components/ConfirmMemberRemoveDialog';
import { ConfirmRevokeInvitationDialog } from '@/features/members/components/ConfirmRevokeInvitationDialog';
import { InviteMemberDialog } from '@/features/members/components/InviteMemberDialog';
import { MembersTable } from '@/features/members/components/MembersTable';
import { PendingInvitations } from '@/features/members/components/PendingInvitations';
import { RolesPanel } from '@/features/members/components/RolesPanel';
import {
  useAssignableRoles,
  useMembersList,
  usePendingInvitations,
  useRemoveMember,
  useResendInvitation,
  useRevokeInvitation,
  useUpdateMemberRole,
  useWorkspaceRoles,
} from '@/features/members/hooks/useMembersQueries';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { WorkspaceInvitationSummary } from '@/services/api/invitations';
import type { Member } from '@/services/api/types';

function ListSkeleton({ testId }: { testId: string }) {
  return (
    <div className="space-y-3 p-5" data-testid={testId}>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-12 rounded bg-muted animate-pulse" />
      ))}
    </div>
  );
}

export function MembersPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { can } = usePermissions();
  const canViewMembers = can(WorkspacePermission.MEMBERS_VIEW);
  const canInvite = can(WorkspacePermission.MEMBERS_INVITE);
  const canChangeRole = can(WorkspacePermission.MEMBERS_UPDATE_ROLE);
  const canRemove = can(WorkspacePermission.MEMBERS_REMOVE);
  const canAssignOwner = can(WorkspacePermission.MEMBERS_PROMOTE_OWNER);
  const canViewRoles = can(WorkspacePermission.ROLES_VIEW);
  const canManageRoles = can(WorkspacePermission.ROLES_MANAGE);

  const membersQuery = useMembersList({ enabled: canViewMembers });
  const invitationsQuery = usePendingInvitations({ enabled: canInvite });
  const assignableQuery = useAssignableRoles({
    enabled: canInvite || canChangeRole,
  });
  const rolesQuery = useWorkspaceRoles({ enabled: canViewRoles || canChangeRole });
  const roleMutation = useUpdateMemberRole();
  const removeMutation = useRemoveMember();
  const resendMutation = useResendInvitation();
  const revokeMutation = useRevokeInvitation();

  const [inviteOpen, setInviteOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<Member | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<WorkspaceInvitationSummary | null>(
    null,
  );

  function handleRoleChange(userId: string, roleId: string) {
    roleMutation.mutate(
      { userId, roleId },
      {
        onSuccess: () => toast.success(t('members.roleUpdated')),
        onError: (err: unknown) => {
          if (err instanceof ApiError) toast.error(t(errorMessageKey(err.code)));
          else toast.error(t('errors.generic'));
        },
      },
    );
  }

  function handleRemoveConfirm() {
    if (!removeTarget) return;
    removeMutation.mutate(removeTarget.user_id, {
      onSuccess: () => {
        toast.success(t('members.removed'));
        setRemoveTarget(null);
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) toast.error(t(errorMessageKey(err.code)));
        else toast.error(t('errors.generic'));
      },
    });
  }

  function handleResend(invitation: WorkspaceInvitationSummary) {
    resendMutation.mutate(invitation.id, {
      onSuccess: () => toast.success(t('members.resent', { email: invitation.email })),
      onError: (err: unknown) => {
        if (err instanceof ApiError) toast.error(t(errorMessageKey(err.code)));
        else toast.error(t('errors.generic'));
      },
    });
  }

  function handleRevokeConfirm() {
    if (!revokeTarget) return;
    revokeMutation.mutate(revokeTarget.id, {
      onSuccess: () => {
        toast.success(t('members.revoked', { email: revokeTarget.email }));
        setRevokeTarget(null);
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) toast.error(t(errorMessageKey(err.code)));
        else toast.error(t('errors.generic'));
      },
    });
  }

  const members = membersQuery.data ?? [];
  const invitations = invitationsQuery.data?.items ?? [];
  const assignableRoles = assignableQuery.data?.items ?? [];
  const ownerRole = (rolesQuery.data?.items ?? []).find((row) => row.is_owner_role) ?? null;
  const defaultTab = canViewMembers ? 'members' : 'roles';

  return (
    <div
      className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto"
      data-testid="members-page"
    >
      <DocumentTitle title={t('members.title')} />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {t('members.eyebrow')}
          </p>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
            {t('members.title')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            {t('members.description')}
          </p>
        </div>
        {canInvite ? (
          <Button
            type="button"
            onClick={() => setInviteOpen(true)}
            data-testid="invite-member-button"
          >
            <UserPlus className="size-3.5" />
            {t('members.invite')}
          </Button>
        ) : null}
      </div>

      <Tabs defaultValue={defaultTab}>
        <TabsList data-testid="members-tabs">
          {canViewMembers ? (
            <TabsTrigger value="members">{t('members.tabs.members')}</TabsTrigger>
          ) : null}
          {canViewRoles ? (
            <TabsTrigger value="roles" data-testid="roles-tab">
              {t('members.tabs.roles')}
            </TabsTrigger>
          ) : null}
        </TabsList>
        {canViewMembers ? (
          <TabsContent value="members" className="space-y-8">
            <Card>
              <CardHeader>
                <CardTitle>{t('members.listTitle')}</CardTitle>
                <CardDescription>
                  {t(
                    members.length === 1
                      ? 'members.memberCountOne'
                      : 'members.memberCount',
                    { count: members.length },
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent className="px-0 pb-0">
                {membersQuery.isLoading ? <ListSkeleton testId="members-loading" /> : null}
                {membersQuery.isError ? (
                  <p className="text-sm text-destructive px-5 py-6">{t('errors.generic')}</p>
                ) : null}
                {!membersQuery.isLoading && !membersQuery.isError ? (
                  <MembersTable
                    members={members}
                    currentUserId={user?.id}
                    assignableRoles={assignableRoles}
                    ownerRole={ownerRole}
                    canChangeRole={canChangeRole}
                    canRemove={canRemove}
                    canAssignOwner={canAssignOwner}
                    busy={roleMutation.isPending || removeMutation.isPending}
                    onChangeRole={handleRoleChange}
                    onRemove={setRemoveTarget}
                  />
                ) : null}
              </CardContent>
            </Card>

            {canInvite ? (
              <Card>
                <CardHeader>
                  <CardTitle>{t('members.pendingTitle')}</CardTitle>
                  <CardDescription>{t('members.pendingDescription')}</CardDescription>
                </CardHeader>
                <CardContent className="px-0 pb-0">
                  {invitationsQuery.isLoading ? (
                    <ListSkeleton testId="invitations-loading" />
                  ) : null}
                  {invitationsQuery.isError ? (
                    <p className="text-sm text-destructive px-5 py-6">{t('errors.generic')}</p>
                  ) : null}
                  {!invitationsQuery.isLoading && !invitationsQuery.isError ? (
                    <PendingInvitations
                      invitations={invitations}
                      busyId={
                        resendMutation.isPending
                          ? (resendMutation.variables ?? null)
                          : revokeMutation.isPending
                            ? (revokeMutation.variables ?? null)
                            : null
                      }
                      onResend={handleResend}
                      onRevoke={setRevokeTarget}
                    />
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
          </TabsContent>
        ) : null}
        {canViewRoles ? (
          <TabsContent value="roles">
            <Card>
              <CardHeader>
                <CardTitle>{t('members.roles.title')}</CardTitle>
                <CardDescription>{t('members.roles.descriptionPage')}</CardDescription>
              </CardHeader>
              <CardContent className="px-0 pb-4">
                <RolesPanel canManage={canManageRoles} />
              </CardContent>
            </Card>
          </TabsContent>
        ) : null}
      </Tabs>

      <InviteMemberDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        onSent={(email) => toast.success(t('members.sent', { email }))}
      />
      <ConfirmMemberRemoveDialog
        member={removeTarget}
        pending={removeMutation.isPending}
        onOpenChange={(open) => {
          if (!open) setRemoveTarget(null);
        }}
        onConfirm={handleRemoveConfirm}
      />
      <ConfirmRevokeInvitationDialog
        invitation={revokeTarget}
        pending={revokeMutation.isPending}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null);
        }}
        onConfirm={handleRevokeConfirm}
      />
    </div>
  );
}
