import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { internalReturnPath } from '@/app/router/guards';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import { AuthLayout } from '@/features/auth/components/AuthLayout';
import { useAuth } from '@/features/auth/AuthProvider';
import { readInvitationToken } from '@/features/members/lib/invitation-path';
import { RoleBadge } from '@/features/members/components/RoleBadge';
import { isLocalDevEnvironment } from '@/features/workspaces/lib/hostname';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  saveWorkspacePreference,
  setWorkspaceContext,
} from '@/services/auth/workspace-context';
import {
  acceptWorkspaceInvitation,
  type InvitationAcceptResult,
} from '@/services/api/invitations';
import type { WorkspaceSummary } from '@/services/api/types';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';

type AcceptState =
  | 'idle'
  | 'accepting'
  | 'success'
  | 'mismatch'
  | 'expired'
  | 'revoked'
  | 'invalid'
  | 'already'
  | 'error';

function stateFromError(err: unknown): AcceptState {
  if (!(err instanceof ApiError)) return 'error';
  switch (err.code) {
    case 'invitation_email_mismatch':
      return 'mismatch';
    case 'invitation_expired':
      return 'expired';
    case 'invitation_revoked':
      return 'revoked';
    case 'invalid_invitation':
    case 'invitation_not_found':
      return 'invalid';
    case 'invitation_already_accepted':
      return 'already';
    default:
      return 'error';
  }
}

function summaryFromAccept(result: InvitationAcceptResult): WorkspaceSummary {
  return {
    id: result.workspace_id,
    name: result.workspace_name,
    slug: result.workspace_slug,
    status: 'active',
    role: result.role,
    permissions: [],
  };
}

export function InvitationAcceptPage() {
  const { t } = useTranslation();
  const { status, user, logout, reloadMe } = useAuth();
  const { selectWorkspace, refreshWorkspaces } = useWorkspace();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const tokenRef = useRef<string | null>(null);
  if (tokenRef.current === null) {
    tokenRef.current = readInvitationToken(searchParams.toString());
  }
  const token = tokenRef.current;

  const [phase, setPhase] = useState<AcceptState>('idle');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [joined, setJoined] = useState<{
    workspace_id: string;
    workspace_name: string;
    role: InvitationAcceptResult['role'];
  } | null>(null);

  const returnTo = useMemo(
    () => internalReturnPath(location),
    [location],
  );

  const acceptCtxRef = useRef({
    user,
    reloadMe,
    refreshWorkspaces,
    selectWorkspace,
    navigate,
    queryClient,
  });
  acceptCtxRef.current = {
    user,
    reloadMe,
    refreshWorkspaces,
    selectWorkspace,
    navigate,
    queryClient,
  };

  useEffect(() => {
    if (status !== 'authenticated' || !token) return;
    let cancelled = false;
    setPhase('accepting');

    async function accept() {
      try {
        const result = await acceptWorkspaceInvitation(token!);
        if (cancelled) return;
        const joinedWorkspace = summaryFromAccept(result);
        setJoined({
          workspace_id: result.workspace_id,
          workspace_name: result.workspace_name,
          role: result.role,
        });
        const ctx = acceptCtxRef.current;
        setWorkspaceContext({
          workspaceId: joinedWorkspace.id,
          workspaceSlug: isLocalDevEnvironment() ? joinedWorkspace.slug : null,
        });
        if (ctx.user) saveWorkspacePreference(ctx.user.id, joinedWorkspace.id);
        await ctx.reloadMe();
        await ctx.queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
        await ctx.queryClient.invalidateQueries({
          queryKey: queryKeys.members(joinedWorkspace.id),
        });
        await ctx.refreshWorkspaces();
        ctx.selectWorkspace(joinedWorkspace.id, joinedWorkspace);
        setPhase('success');
        ctx.navigate('/', { replace: true });
      } catch (err) {
        if (cancelled) return;
        const next = stateFromError(err);
        setPhase(next);
        if (err instanceof ApiError) {
          setErrorKey(errorMessageKey(err.code));
        } else {
          setErrorKey('errors.generic');
        }
      }
    }

    void accept();
    return () => {
      cancelled = true;
    };
  }, [status, token]);

  async function signOutForOtherAccount() {
    await logout();
    navigate('/login', { replace: true, state: { from: returnTo } });
  }

  if (status === 'bootstrapping') {
    return (
      <AuthLayout>
        <DocumentTitle title={t('invitations.title')} />
        <div className="flex justify-center py-12" data-testid="invitation-accept-loading">
          <LoaderCircle className="size-6 animate-spin text-muted-foreground" />
        </div>
      </AuthLayout>
    );
  }

  if (!token) {
    return (
      <AuthLayout>
        <DocumentTitle title={t('invitations.title')} />
        <InvitationCard
          title={t('invitations.title')}
          body={t('invitations.invalid')}
          testId="invitation-invalid"
        />
      </AuthLayout>
    );
  }

  if (status === 'unauthenticated') {
    return (
      <AuthLayout>
        <DocumentTitle title={t('invitations.title')} />
        <div className="space-y-5" data-testid="invitation-accept-guest">
          <div className="space-y-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              {t('invitations.eyebrow')}
            </p>
            <h1 className="text-xl font-semibold tracking-tight">{t('invitations.title')}</h1>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {t('invitations.guestBody')}
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Button asChild>
              <Link
                to="/login"
                replace
                state={{ from: returnTo }}
                data-testid="invitation-login"
              >
                {t('invitations.signInToContinue')}
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link
                to="/register"
                replace
                state={{ from: returnTo }}
                data-testid="invitation-register"
              >
                {t('invitations.registerToContinue')}
              </Link>
            </Button>
          </div>
        </div>
      </AuthLayout>
    );
  }

  if (phase === 'accepting' || phase === 'idle') {
    return (
      <AuthLayout>
        <DocumentTitle title={t('invitations.title')} />
        <div className="space-y-3" data-testid="invitation-accepting">
          <h1 className="text-xl font-semibold tracking-tight">{t('invitations.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('invitations.accepting')}</p>
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
        </div>
      </AuthLayout>
    );
  }

  if (phase === 'success' && joined) {
    return (
      <AuthLayout>
        <DocumentTitle title={t('invitations.title')} />
        <div className="space-y-4" data-testid="invitation-success">
          <h1 className="text-xl font-semibold">{t('invitations.successTitle')}</h1>
          <p className="text-sm text-muted-foreground">
            {t('invitations.successBody', { name: joined.workspace_name })}
          </p>
          <RoleBadge role={joined.role} />
        </div>
      </AuthLayout>
    );
  }

  const copy =
    phase === 'mismatch'
      ? {
          title: t('invitations.mismatchTitle'),
          body: t('invitations.emailMismatch'),
          testId: 'invitation-mismatch',
        }
      : phase === 'expired'
        ? {
            title: t('invitations.expiredTitle'),
            body: t('invitations.expired'),
            testId: 'invitation-expired',
          }
        : phase === 'revoked'
          ? {
              title: t('invitations.revokedTitle'),
              body: t('invitations.revoked'),
              testId: 'invitation-revoked',
            }
          : phase === 'already'
            ? {
                title: t('invitations.alreadyTitle'),
                body: t('invitations.alreadyAccepted'),
                testId: 'invitation-already',
              }
            : {
                title: t('invitations.invalidTitle'),
                body: t(errorKey ?? 'invitations.invalid'),
                testId: 'invitation-invalid',
              };

  return (
    <AuthLayout>
      <DocumentTitle title={t('invitations.title')} />
      <div className="space-y-5" data-testid={copy.testId}>
        <InvitationCard title={copy.title} body={copy.body} />
        {phase === 'mismatch' ? (
          <Button
            type="button"
            onClick={() => void signOutForOtherAccount()}
            data-testid="invitation-use-another-account"
          >
            {t('invitations.useAnotherAccount')}
          </Button>
        ) : (
          <Button asChild variant="outline">
            <Link to="/">{t('invitations.goHome')}</Link>
          </Button>
        )}
      </div>
    </AuthLayout>
  );
}

function InvitationCard({
  title,
  body,
  testId,
}: {
  title: string;
  body: string;
  testId?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2" data-testid={testId}>
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {t('app.name')}
      </p>
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      <AuthAlert tone="warning">{body}</AuthAlert>
    </div>
  );
}
