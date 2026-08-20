import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  AppWindow,
  ArrowLeft,
  ArrowUpRight,
  Building2,
  CheckCircle2,
  CircleAlert,
  Crown,
  HardDrive,
  KeyRound,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import {
  UserStatusBadge,
  WorkspaceKindBadge,
  WorkspaceStatusBadge,
} from '@/components/shared/StatusBadges';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { WorkspaceBillingSection } from '@/features/workspaces/components/WorkspaceBillingSection';
import { formatAdminDate, formatAdminDateTime, formatBytes } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  disablePlatformWorkspace,
  enablePlatformWorkspace,
  fetchPlatformWorkspace,
  fetchPlatformWorkspaceMembers,
  platformQueryKeys,
} from '@/services/api/platform';
import type { PlatformWorkspaceMember } from '@/services/api/types';

const MEMBERS_PAGE_SIZE = 10;

export function WorkspaceDetailPage() {
  const { workspaceId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<'disable' | 'enable' | null>(null);
  const [memberOffset, setMemberOffset] = useState(0);

  useEffect(() => {
    setMemberOffset(0);
  }, [workspaceId]);

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.workspace(workspaceId),
    queryFn: () => fetchPlatformWorkspace(workspaceId),
    enabled: Boolean(workspaceId),
  });

  const memberFilters = { limit: MEMBERS_PAGE_SIZE, offset: memberOffset };
  const membersQuery = useQuery({
    queryKey: platformQueryKeys.workspaceMembers(workspaceId, memberFilters),
    queryFn: () => fetchPlatformWorkspaceMembers(workspaceId, memberFilters),
    enabled: Boolean(workspaceId),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['platform', 'workspaces'] });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.workspace(workspaceId) });
    await queryClient.invalidateQueries({
      queryKey: ['platform', 'workspace', workspaceId, 'members'],
    });
  };

  const disableMutation = useMutation({
    mutationFn: (reason: string) => disablePlatformWorkspace(workspaceId, reason),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('workspaces.disableSuccess'));
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const enableMutation = useMutation({
    mutationFn: (reason: string) => enablePlatformWorkspace(workspaceId, reason || undefined),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('workspaces.enableSuccess'));
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  if (detailQuery.isLoading) {
    return <WorkspaceDetailSkeleton />;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8">
        <Link
          to="/workspaces"
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
          {t('workspaces.backToList')}
        </Link>
        <Card data-testid="workspace-detail-error">
          <CardContent className="flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center">
            <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <CircleAlert className="size-5" aria-hidden />
            </span>
            <h1 className="text-base font-semibold">{t('workspaces.detailErrorTitle')}</h1>
            <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
              {getErrorMessage(detailQuery.error, t)}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-5"
              onClick={() => void detailQuery.refetch()}
            >
              <RefreshCw className="size-3.5" aria-hidden />
              {t('common.retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const workspace = detailQuery.data;
  const isSystem = workspace.kind === 'system';
  const isSuspended = workspace.status === 'suspended';
  const isActive = workspace.status === 'active';
  const lifecyclePending = disableMutation.isPending || enableMutation.isPending;

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="workspace-detail-page"
    >
      <DocumentTitle title={workspace.name} />

      <Link
        to="/workspaces"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
        {t('workspaces.backToList')}
      </Link>

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.09] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-20 -top-24 size-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <span
              className={cn(
                'flex size-12 shrink-0 items-center justify-center rounded-2xl border shadow-xs md:size-14',
                isSystem
                  ? 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/60 dark:text-violet-300'
                  : 'border-primary/15 bg-background/85 text-primary',
              )}
              aria-hidden
            >
              {isSystem ? <ShieldCheck className="size-6" /> : <Building2 className="size-6" />}
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                {t('workspaces.detailEyebrow')}
              </p>
              <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight md:text-3xl">
                {workspace.name}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="rounded-md border border-border bg-background/70 px-2 py-1 font-mono text-xs text-muted-foreground">
                  {workspace.slug}
                </span>
                <WorkspaceStatusBadge status={workspace.status} />
                <WorkspaceKindBadge kind={workspace.kind} />
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            {!isSystem && isActive ? (
              <Button
                variant="destructive"
                onClick={() => setDialog('disable')}
                disabled={lifecyclePending}
                data-testid="workspace-disable-button"
              >
                <PauseCircle className="size-4" aria-hidden />
                {t('workspaces.disable')}
              </Button>
            ) : null}
            {!isSystem && isSuspended ? (
              <Button
                onClick={() => setDialog('enable')}
                disabled={lifecyclePending}
                data-testid="workspace-enable-button"
              >
                <PlayCircle className="size-4" aria-hidden />
                {t('workspaces.enable')}
              </Button>
            ) : null}
          </div>
        </div>

        {isSystem ? (
          <div
            className="relative mt-5 flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50/80 p-3.5 text-violet-950 dark:border-violet-900 dark:bg-violet-950/45 dark:text-violet-100"
            data-testid="workspace-system-protected"
          >
            <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div>
              <p className="text-sm font-semibold">{t('workspaces.systemProtectedTitle')}</p>
              <p className="mt-0.5 text-xs leading-5 opacity-75">{t('workspaces.systemProtected')}</p>
            </div>
          </div>
        ) : null}

        {isSuspended ? (
          <div
            className="relative mt-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50/90 p-3.5 text-amber-950 dark:border-amber-900 dark:bg-amber-950/45 dark:text-amber-100"
            data-testid="workspace-access-suspended"
          >
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div>
              <p className="text-sm font-semibold">{t('workspaces.accessSuspendedTitle')}</p>
              <p className="mt-0.5 text-xs leading-5 opacity-75">
                {t('workspaces.accessSuspendedHint')}
              </p>
            </div>
          </div>
        ) : null}
      </section>

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('workspaces.resourceSummary')}
        data-testid="workspace-resource-summary"
      >
        <ResourceMetric
          icon={UsersRound}
          label={t('workspaces.members')}
          value={workspace.resources.members_count.toLocaleString(i18n.language)}
          hint={t('workspaces.metricHints.members')}
          tone="primary"
        />
        <ResourceMetric
          icon={Sparkles}
          label={t('workspaces.experts')}
          value={workspace.resources.experts_count.toLocaleString(i18n.language)}
          hint={t('workspaces.metricHints.experts')}
          tone="info"
        />
        <ResourceMetric
          icon={KeyRound}
          label={t('workspaces.apiKeys')}
          value={workspace.resources.api_keys_count.toLocaleString(i18n.language)}
          hint={t('workspaces.metricHints.apiKeys')}
          tone="warning"
        />
        <ResourceMetric
          icon={AppWindow}
          label={t('workspaces.appInstallations')}
          value={workspace.resources.app_installations_count.toLocaleString(i18n.language)}
          hint={t('workspaces.metricHints.apps')}
          tone="success"
        />
      </section>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.8fr)]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t('workspaces.overview')}</CardTitle>
                <CardDescription>{t('workspaces.profileDescription')}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <DefinitionItem
                  label={t('workspaces.workspaceId')}
                  value={<span className="font-mono text-xs">{workspace.id}</span>}
                />
                <DefinitionItem
                  label={t('workspaces.slug')}
                  value={<span className="font-mono text-xs">{workspace.slug}</span>}
                />
                <DefinitionItem
                  label={t('workspaces.created')}
                  value={formatAdminDateTime(workspace.created_at, i18n.language)}
                />
                <DefinitionItem
                  label={t('workspaces.updated')}
                  value={formatAdminDateTime(workspace.updated_at, i18n.language)}
                />
                <DefinitionItem
                  label={t('workspaces.createdBy')}
                  value={
                    workspace.created_by ? (
                      <Link
                        to={`/users/${workspace.created_by}`}
                        className="inline-flex min-w-0 items-center gap-1 font-mono text-xs text-primary hover:underline"
                      >
                        <span className="truncate">{workspace.created_by}</span>
                        <ArrowUpRight className="size-3 shrink-0 rtl:-scale-x-100" aria-hidden />
                      </Link>
                    ) : (
                      t('common.none')
                    )
                  }
                />
                <DefinitionItem
                  label={t('common.status')}
                  value={<WorkspaceStatusBadge status={workspace.status} />}
                />
              </div>

              <Separator />

              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold">{t('workspaces.owners')}</h3>
                  <Badge variant="secondary" appearance="light" size="sm">
                    {workspace.owners.length.toLocaleString(i18n.language)}
                  </Badge>
                </div>
                {workspace.owners.length > 0 ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {workspace.owners.map((owner) => (
                      <Link
                        key={owner.membership_id}
                        to={`/users/${owner.user_id}`}
                        className="group flex min-w-0 items-center gap-3 rounded-xl border border-border p-3 transition-colors hover:bg-muted/40"
                      >
                        <Avatar className="size-9">
                          <AvatarFallback className="bg-primary/10 font-semibold text-primary">
                            {initials(owner.email)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium group-hover:text-primary">
                            {owner.email}
                          </p>
                          <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                            <Crown className="size-3 text-amber-500" aria-hidden />
                            {owner.role_name || t('workspaces.ownerRole')}
                          </p>
                        </div>
                        <ArrowUpRight
                          className="size-3.5 shrink-0 text-muted-foreground rtl:-scale-x-100"
                          aria-hidden
                        />
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
                    {t('workspaces.noOwners')}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t('workspaces.membersSection')}</CardTitle>
                <CardDescription>{t('workspaces.membersDescription')}</CardDescription>
              </CardHeading>
              <CardToolbar>
                <Badge variant="secondary" appearance="light" data-testid="workspace-member-total">
                  {(membersQuery.data?.total ?? workspace.members_count).toLocaleString(i18n.language)}
                </Badge>
              </CardToolbar>
            </CardHeader>
            <CardContent className="p-0">
              {membersQuery.isLoading ? (
                <MemberListSkeleton />
              ) : membersQuery.isError ? (
                <div className="flex min-h-44 flex-col items-center justify-center px-5 py-8 text-center">
                  <CircleAlert className="mb-3 size-5 text-destructive" aria-hidden />
                  <p className="text-sm font-medium">{t('workspaces.membersError')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {getErrorMessage(membersQuery.error, t)}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-4"
                    onClick={() => void membersQuery.refetch()}
                  >
                    <RefreshCw className="size-3.5" aria-hidden />
                    {t('common.retry')}
                  </Button>
                </div>
              ) : membersQuery.data?.items.length === 0 ? (
                <div className="flex min-h-44 flex-col items-center justify-center px-5 py-8 text-center">
                  <span className="mb-3 flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <UsersRound className="size-4" aria-hidden />
                  </span>
                  <p className="text-sm font-medium">{t('workspaces.noMembers')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('workspaces.noMembersHint')}
                  </p>
                </div>
              ) : (
                <ul className="divide-y divide-border" data-testid="workspace-members-list">
                  {membersQuery.data?.items.map((member) => (
                    <MemberRow key={member.membership_id} member={member} locale={i18n.language} />
                  ))}
                </ul>
              )}
            </CardContent>
            {membersQuery.data && membersQuery.data.total > membersQuery.data.limit ? (
              <CardFooter className="py-3">
                <AdminPagination
                  total={membersQuery.data.total}
                  limit={membersQuery.data.limit}
                  offset={membersQuery.data.offset}
                  onPageChange={setMemberOffset}
                  testId="workspace-members-pagination"
                />
              </CardFooter>
            ) : null}
          </Card>
        </div>

        <aside className="min-w-0 space-y-5">
          <StorageCard
            used={workspace.resources.storage_used_bytes}
            limit={workspace.resources.storage_limit_bytes}
            locale={i18n.language}
          />
          <AccessCard kind={workspace.kind} status={workspace.status} />
        </aside>
      </div>

      <WorkspaceBillingSection
        workspaceId={workspaceId}
        workspaceName={workspace.name}
        isSystem={isSystem}
      />

      <LifecycleDialog
        open={dialog === 'disable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('workspaces.disableTitle')}
        description={t('workspaces.disableHint')}
        reasonRequired
        confirmLabel={t('workspaces.disable')}
        pending={disableMutation.isPending}
        onConfirm={(reason) => disableMutation.mutate(reason)}
        testId="workspace-disable-dialog"
      />
      <LifecycleDialog
        open={dialog === 'enable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('workspaces.enableTitle')}
        description={t('workspaces.enableHint')}
        reasonRequired={false}
        confirmLabel={t('workspaces.enable')}
        confirmVariant="primary"
        pending={enableMutation.isPending}
        onConfirm={(reason) => enableMutation.mutate(reason)}
        testId="workspace-enable-dialog"
      />
    </div>
  );
}

function StorageCard({
  used,
  limit,
  locale,
}: {
  used: number | null | undefined;
  limit: number | null | undefined;
  locale: string;
}) {
  const { t } = useTranslation();
  const hasStorage = used != null && limit != null;
  const percent = hasStorage && limit > 0 ? Math.min(100, Math.max(0, (used / limit) * 100)) : 0;
  const remaining = hasStorage ? Math.max(0, limit - used) : null;

  return (
    <Card data-testid="workspace-storage-card">
      <CardHeader>
        <CardHeading>
          <CardTitle>{t('workspaces.storageSection')}</CardTitle>
          <CardDescription>{t('workspaces.storageDescription')}</CardDescription>
        </CardHeading>
        <CardToolbar>
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <HardDrive className="size-4" aria-hidden />
          </span>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {hasStorage ? (
          <div className="space-y-4">
            <div>
              <div className="mb-2 flex items-end justify-between gap-4">
                <div>
                  <p className="text-xl font-semibold tabular-nums">{formatBytes(used, locale)}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {t('workspaces.ofStorage', { total: formatBytes(limit, locale) })}
                  </p>
                </div>
                <p className="text-sm font-semibold tabular-nums">
                  {percent.toLocaleString(locale, { maximumFractionDigits: 1 })}%
                </p>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-muted"
                role="progressbar"
                aria-label={t('workspaces.storageUsed')}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(percent)}
              >
                <div
                  className={cn(
                    'h-full rounded-full transition-[width]',
                    percent >= 90 ? 'bg-destructive' : percent >= 75 ? 'bg-amber-500' : 'bg-primary',
                  )}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
            <DefinitionItem
              label={t('workspaces.storageRemaining')}
              value={formatBytes(remaining, locale)}
            />
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {t('workspaces.storageUnavailable')}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AccessCard({ kind, status }: { kind: string; status: string }) {
  const { t } = useTranslation();
  const isSystem = kind === 'system';
  const isSuspended = status === 'suspended';
  const Icon = isSystem ? ShieldCheck : isSuspended ? PauseCircle : CheckCircle2;
  const tone = isSystem
    ? 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300'
    : isSuspended
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300'
      : 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300';
  const title = isSystem
    ? t('workspaces.accessSystemTitle')
    : isSuspended
      ? t('workspaces.accessSuspendedTitle')
      : t('workspaces.accessActiveTitle');
  const description = isSystem
    ? t('workspaces.accessSystemHint')
    : isSuspended
      ? t('workspaces.accessSuspendedHint')
      : t('workspaces.accessActiveHint');

  return (
    <Card data-testid="workspace-access-card">
      <CardHeader>
        <CardHeading>
          <CardTitle>{t('workspaces.accessSection')}</CardTitle>
          <CardDescription>{t('workspaces.accessDescription')}</CardDescription>
        </CardHeading>
      </CardHeader>
      <CardContent>
        <div className="flex items-start gap-3">
          <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', tone)}>
            <Icon className="size-5" aria-hidden />
          </span>
          <div>
            <p className="text-sm font-semibold">{title}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function MemberRow({ member, locale }: { member: PlatformWorkspaceMember; locale: string }) {
  const { t } = useTranslation();

  return (
    <li
      className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
      data-testid="workspace-member-row"
    >
      <div className="flex min-w-0 items-center gap-3">
        <Avatar className="size-9">
          <AvatarFallback className="bg-primary/10 font-semibold text-primary">
            {initials(member.email)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <Link
            to={`/users/${member.user_id}`}
            className="block truncate text-sm font-medium hover:text-primary hover:underline"
          >
            {member.email}
          </Link>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t('workspaces.memberSince', {
              date: formatAdminDate(member.created_at, locale),
            })}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 ps-12 sm:ps-0">
        <Badge variant={member.is_owner_role ? 'warning' : 'secondary'} appearance="light" size="sm">
          {member.is_owner_role ? <Crown className="size-3" aria-hidden /> : null}
          {member.role_name || t('common.none')}
        </Badge>
        <UserStatusBadge status={member.user_status} />
        <Link
          to={`/users/${member.user_id}`}
          className="ms-auto flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:ms-0"
          aria-label={t('workspaces.viewMember', { email: member.email })}
        >
          <ArrowUpRight className="size-3.5 rtl:-scale-x-100" aria-hidden />
        </Link>
      </div>
    </li>
  );
}

type MetricTone = 'primary' | 'success' | 'warning' | 'info';

function ResourceMetric({
  icon: Icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint: string;
  tone: MetricTone;
}) {
  const tones: Record<MetricTone, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
    warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
    info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
  };

  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', tones[tone])}>
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-xl font-semibold tabular-nums">{value}</p>
          <p className="text-xs font-medium">{label}</p>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{hint}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function DefinitionItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-1 min-w-0 break-words text-sm font-medium">{value}</div>
    </div>
  );
}

function MemberListSkeleton() {
  return (
    <div data-testid="workspace-members-loading">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="flex items-center gap-3 border-b border-border px-5 py-4 last:border-0">
          <div className="size-9 shrink-0 animate-pulse rounded-full bg-muted" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3.5 w-44 animate-pulse rounded bg-muted" />
            <div className="h-3 w-28 animate-pulse rounded bg-muted" />
          </div>
          <div className="hidden h-5 w-20 animate-pulse rounded bg-muted sm:block" />
        </div>
      ))}
    </div>
  );
}

function WorkspaceDetailSkeleton() {
  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="workspace-detail-loading"
    >
      <div className="h-5 w-36 animate-pulse rounded bg-muted" />
      <div className="h-44 animate-pulse rounded-2xl bg-muted" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-24 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.8fr)]">
        <div className="h-80 animate-pulse rounded-xl bg-muted" />
        <div className="h-64 animate-pulse rounded-xl bg-muted" />
      </div>
    </div>
  );
}

function initials(value: string): string {
  const localPart = value.trim().split('@')[0] || value.trim();
  const parts = localPart.split(/[._\-\s]+/).filter(Boolean);
  return (parts.slice(0, 2).map((part) => part[0]).join('') || '?').toUpperCase();
}
