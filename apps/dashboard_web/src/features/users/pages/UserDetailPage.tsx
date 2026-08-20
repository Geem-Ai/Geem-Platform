import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  ArrowLeft,
  ArrowUpRight,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Crown,
  KeyRound,
  MailCheck,
  MailWarning,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import {
  PlatformRoleBadge,
  UserStatusBadge,
  WorkspaceStatusBadge,
} from '@/components/shared/StatusBadges';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { useAuth } from '@/features/auth/AuthProvider';
import { formatAdminDate, formatAdminDateTime } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  disablePlatformUser,
  enablePlatformUser,
  fetchPlatformUser,
  platformQueryKeys,
} from '@/services/api/platform';
import type { PlatformUserMembership } from '@/services/api/types';

export function UserDetailPage() {
  const { userId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<'disable' | 'enable' | null>(null);

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.user(userId),
    queryFn: () => fetchPlatformUser(userId),
    enabled: Boolean(userId),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['platform', 'users'] });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.user(userId) });
  };

  const disableMutation = useMutation({
    mutationFn: (reason: string) => disablePlatformUser(userId, reason),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('users.disableSuccess'));
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const enableMutation = useMutation({
    mutationFn: (reason: string) => enablePlatformUser(userId, reason || undefined),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('users.enableSuccess'));
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  if (detailQuery.isLoading) {
    return <UserDetailSkeleton />;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8">
        <DocumentTitle title={t('users.title')} />
        <Link
          to="/users"
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
          {t('users.backToList')}
        </Link>
        <Card data-testid="user-detail-error">
          <CardContent className="flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center">
            <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <CircleAlert className="size-5" aria-hidden />
            </span>
            <h1 className="text-base font-semibold">{t('users.detailErrorTitle')}</h1>
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

  const user = detailQuery.data;
  const isSelf = me?.id === user.id;
  const isActive = user.status === 'active';
  const isDisabled = user.status === 'disabled';
  const isVerified = Boolean(user.email_verified_at);
  const currentMembershipCount = user.memberships.filter(
    (membership) => membership.workspace_status !== 'archived',
  ).length;
  const lifecyclePending = disableMutation.isPending || enableMutation.isPending;

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="user-detail-page"
    >
      <DocumentTitle title={user.email} />

      <Link
        to="/users"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
        {t('users.backToList')}
      </Link>

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.09] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-20 -top-24 size-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <Avatar className="size-12 md:size-14">
              <AvatarFallback className="border-primary/15 bg-background/85 text-base font-semibold text-primary shadow-xs">
                {initials(user.email)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
                {t('users.detailEyebrow')}
              </p>
              <h1 className="mt-1 break-words text-2xl font-semibold tracking-tight md:text-3xl">
                <bdi dir="ltr">{user.email}</bdi>
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <UserStatusBadge status={user.status} />
                <PlatformRoleBadge role={user.platform_role} />
                <Badge
                  variant={isVerified ? 'success' : 'warning'}
                  appearance="light"
                  size="sm"
                >
                  {isVerified ? (
                    <MailCheck className="size-3" aria-hidden />
                  ) : (
                    <MailWarning className="size-3" aria-hidden />
                  )}
                  {isVerified ? t('users.verified') : t('users.unverified')}
                </Badge>
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            {!isSelf && isActive ? (
              <Button
                variant="destructive"
                onClick={() => setDialog('disable')}
                disabled={lifecyclePending}
                data-testid="user-disable-button"
              >
                <PauseCircle className="size-4" aria-hidden />
                {t('users.disable')}
              </Button>
            ) : null}
            {!isSelf && isDisabled ? (
              <Button
                onClick={() => setDialog('enable')}
                disabled={lifecyclePending}
                data-testid="user-enable-button"
              >
                <PlayCircle className="size-4" aria-hidden />
                {t('users.enable')}
              </Button>
            ) : null}
          </div>
        </div>

        {isSelf ? (
          <div
            className="relative mt-5 flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50/80 p-3.5 text-violet-950 dark:border-violet-900 dark:bg-violet-950/45 dark:text-violet-100"
            data-testid="user-self-protected"
          >
            <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div>
              <p className="text-sm font-semibold">{t('users.selfProtectedTitle')}</p>
              <p className="mt-0.5 text-xs leading-5 opacity-75">{t('users.selfProtected')}</p>
            </div>
          </div>
        ) : null}
      </section>

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('users.resourceSummary')}
        data-testid="user-resource-summary"
      >
        <SummaryMetric
          icon={Building2}
          label={t('users.workspacesSection')}
          value={currentMembershipCount.toLocaleString(i18n.language)}
          hint={t('users.metricHints.memberships')}
          tone="primary"
        />
        <SummaryMetric
          icon={KeyRound}
          label={t('users.activeSessions')}
          value={user.active_session_count.toLocaleString(i18n.language)}
          hint={t('users.metricHints.sessions')}
          tone="info"
        />
        <SummaryMetric
          icon={isVerified ? MailCheck : MailWarning}
          label={t('users.emailVerified')}
          value={isVerified ? t('users.verified') : t('users.unverified')}
          hint={t('users.metricHints.verification')}
          tone={isVerified ? 'success' : 'warning'}
        />
        <SummaryMetric
          icon={Clock3}
          label={t('users.lastLogin')}
          value={
            user.last_login_at
              ? formatAdminDate(user.last_login_at, i18n.language)
              : t('users.neverActive')
          }
          hint={t('users.metricHints.activity')}
          tone="neutral"
        />
      </section>

      <div className="grid items-stretch gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <div className="min-w-0">
          <Card className="h-full" data-testid="user-account-overview">
            <CardHeader className="items-start py-5 md:px-6 sm:flex-nowrap">
              <CardHeading>
                <CardTitle>{t('users.accountOverview')}</CardTitle>
                <CardDescription>{t('users.accountOverviewDescription')}</CardDescription>
              </CardHeading>
              <CardToolbar>
                <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <UsersRound className="size-4" aria-hidden />
                </span>
              </CardToolbar>
            </CardHeader>
            <CardContent className="px-5 py-6 md:px-6 md:py-7">
              <div className="grid gap-x-8 gap-y-7 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <DefinitionItem
                    label={t('users.userId')}
                    value={
                      <bdi dir="ltr" className="font-mono text-sm">
                        {user.id}
                      </bdi>
                    }
                  />
                </div>
                <DefinitionItem
                  label={t('users.created')}
                  value={formatAdminDateTime(user.created_at, i18n.language)}
                />
                <DefinitionItem
                  label={t('users.updated')}
                  value={formatAdminDateTime(user.updated_at, i18n.language)}
                />
                {user.deleted_at ? (
                  <DefinitionItem
                    label={t('users.deleted')}
                    value={formatAdminDateTime(user.deleted_at, i18n.language)}
                  />
                ) : null}
              </div>
            </CardContent>
          </Card>
        </div>

        <aside className="min-w-0">
          <Card className="h-full" data-testid="user-lifecycle-summary">
            <CardHeader className="items-start py-5 md:px-6">
              <CardHeading>
                <CardTitle>{t('users.lifecycleSection')}</CardTitle>
                <CardDescription>{t('users.lifecycleDescription')}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="flex grow items-center px-5 py-6 md:px-6 md:py-7">
              <div className="flex items-start gap-4">
                <span
                  className={cn(
                    'flex size-11 shrink-0 items-center justify-center rounded-xl',
                    isActive
                      ? 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300'
                      : 'bg-red-100 text-red-700 dark:bg-red-950/70 dark:text-red-300',
                  )}
                >
                  {isActive ? (
                    <CheckCircle2 className="size-5.5" aria-hidden />
                  ) : (
                    <ShieldOff className="size-5.5" aria-hidden />
                  )}
                </span>
                <div className="min-w-0">
                  <p className="text-base font-semibold leading-6">
                    {isActive ? t('users.accessActiveTitle') : t('users.accessDisabledTitle')}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {isActive ? t('users.accessActiveHint') : t('users.accessDisabledHint')}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>

      <Card data-testid="user-memberships-card">
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('users.workspacesSection')}</CardTitle>
            <CardDescription>{t('users.membershipsDescription')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            <Badge variant="secondary" appearance="light">
              {t('users.membershipCount', { count: user.memberships.length })}
            </Badge>
          </CardToolbar>
        </CardHeader>
        <CardContent className="p-0">
          {user.memberships.length === 0 ? (
            <div className="flex min-h-48 flex-col items-center justify-center px-5 py-9 text-center">
              <span className="mb-3 flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Building2 className="size-5" aria-hidden />
              </span>
              <p className="text-sm font-semibold">{t('users.noWorkspacesTitle')}</p>
              <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
                {t('users.noWorkspaces')}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-border" data-testid="user-memberships-list">
              {user.memberships.map((membership) => (
                <MembershipRow
                  key={membership.membership_id}
                  membership={membership}
                  locale={i18n.language}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <LifecycleDialog
        open={dialog === 'disable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('users.disableTitle')}
        description={t('users.disableHint')}
        reasonRequired
        confirmLabel={t('users.disable')}
        pending={disableMutation.isPending}
        onConfirm={(reason) => disableMutation.mutate(reason)}
        testId="user-disable-dialog"
      />
      <LifecycleDialog
        open={dialog === 'enable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('users.enableTitle')}
        description={t('users.enableHint')}
        reasonRequired={false}
        confirmLabel={t('users.enable')}
        confirmVariant="primary"
        pending={enableMutation.isPending}
        onConfirm={(reason) => enableMutation.mutate(reason)}
        testId="user-enable-dialog"
      />
    </div>
  );
}

type MetricTone = 'primary' | 'success' | 'warning' | 'info' | 'neutral';

function SummaryMetric({
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
    neutral: 'bg-muted text-muted-foreground',
  };

  return (
    <Card className="min-h-28">
      <CardContent className="flex items-center gap-4 p-4">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', tones[tone])}>
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold tabular-nums">{value}</p>
          <p className="truncate text-xs font-medium">{label}</p>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{hint}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function MembershipRow({
  membership,
  locale,
}: {
  membership: PlatformUserMembership;
  locale: string;
}) {
  const { t } = useTranslation();

  return (
    <li
      className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
      data-testid="user-membership-row"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-primary/15 bg-primary/8 text-primary">
          <Building2 className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <Link
            to={`/workspaces/${membership.workspace_id}`}
            className="block truncate text-sm font-semibold transition-colors hover:text-primary hover:underline"
          >
            {membership.workspace_name}
          </Link>
          <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
            <bdi dir="ltr">{membership.workspace_slug}</bdi>
          </p>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <CalendarDays className="size-3 shrink-0" aria-hidden />
            {t('users.memberSince', {
              date: formatAdminDate(membership.created_at, locale),
            })}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 ps-[3.25rem] sm:ps-0">
        <Badge variant="secondary" appearance="light" size="sm">
          {membership.role_name || t('common.none')}
        </Badge>
        {membership.is_owner_role ? (
          <Badge variant="warning" appearance="light" size="sm">
            <Crown className="size-3" aria-hidden />
            {t('users.ownerBadge')}
          </Badge>
        ) : null}
        <WorkspaceStatusBadge status={membership.workspace_status} />
        <Link
          to={`/workspaces/${membership.workspace_id}`}
          className="ms-auto flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:ms-0"
          aria-label={t('users.viewWorkspace', { name: membership.workspace_name })}
        >
          <ArrowUpRight className="size-3.5 rtl:-scale-x-100" aria-hidden />
        </Link>
      </div>
    </li>
  );
}

function DefinitionItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-2 min-w-0 break-words text-sm font-medium leading-6">{value}</div>
    </div>
  );
}

function UserDetailSkeleton() {
  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="user-detail-loading"
    >
      <div className="h-5 w-36 animate-pulse rounded bg-muted" />
      <div className="h-44 animate-pulse rounded-2xl bg-muted" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
      <div className="grid items-stretch gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <div className="h-64 animate-pulse rounded-xl bg-muted" />
        <div className="h-64 animate-pulse rounded-xl bg-muted" />
      </div>
      <div className="h-64 animate-pulse rounded-xl bg-muted" />
    </div>
  );
}

function initials(value: string): string {
  const localPart = value.trim().split('@')[0] || value.trim();
  const parts = localPart.split(/[._\-\s]+/).filter(Boolean);
  return (parts.slice(0, 2).map((part) => part[0]).join('') || '?').toUpperCase();
}
