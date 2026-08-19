import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthProvider';
import { ForbiddenPage } from '@/features/authz/pages/ForbiddenPage';
import { usePermissions } from '@/features/authz/usePermissions';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ScreenLoader } from '@/components/shared/ScreenLoader';

const PAYMENT_RETURN_STORAGE_KEY = 'geem.billing.paymentReturn';
const AUTH_CONTINUE_STORAGE_KEY = 'geem.auth.continueFrom';

/** Same-origin relative path including search (payment result needs ?purchase=). */
export function internalReturnPath(location: {
  pathname: string;
  search: string;
}): string {
  return `${location.pathname}${location.search}`;
}

export function safeInternalPath(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  if (!raw.startsWith('/') || raw.startsWith('//')) return null;
  return raw;
}

export function isBillingPaymentResultPath(pathname: string): boolean {
  return pathname.startsWith('/billing/payment/');
}

export function rememberPaymentReturn(location: {
  pathname: string;
  search: string;
}): void {
  if (typeof sessionStorage === 'undefined') return;
  if (!isBillingPaymentResultPath(location.pathname)) return;
  sessionStorage.setItem(
    PAYMENT_RETURN_STORAGE_KEY,
    internalReturnPath(location),
  );
}

export function consumePaymentReturn(): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  const raw = sessionStorage.getItem(PAYMENT_RETURN_STORAGE_KEY);
  if (!raw) return null;
  sessionStorage.removeItem(PAYMENT_RETURN_STORAGE_KEY);
  return safeInternalPath(raw);
}

/** Keep invitation/payment return across the email-verification hop. */
export function rememberAuthContinue(from: unknown): void {
  if (typeof sessionStorage === 'undefined') return;
  const path = safeInternalPath(from);
  if (!path) return;
  sessionStorage.setItem(AUTH_CONTINUE_STORAGE_KEY, path);
}

export function consumeAuthContinue(): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  const raw = sessionStorage.getItem(AUTH_CONTINUE_STORAGE_KEY);
  if (!raw) return null;
  sessionStorage.removeItem(AUTH_CONTINUE_STORAGE_KEY);
  return safeInternalPath(raw);
}

/** Login/onboarding continue target. Prefers `from`, then stashed payment return. */
export function continueAfterAuth(from: unknown): string {
  const explicit = safeInternalPath(from);
  const pathOnly = explicit?.split('?')[0] ?? null;
  if (
    explicit &&
    pathOnly &&
    pathOnly !== '/login' &&
    pathOnly !== '/register' &&
    pathOnly !== '/forgot-password' &&
    pathOnly !== '/reset-password' &&
    pathOnly !== '/check-email' &&
    pathOnly !== '/verify-email' &&
    pathOnly !== '/onboarding'
  ) {
    if (isBillingPaymentResultPath(pathOnly)) {
      consumePaymentReturn();
    }
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.removeItem(AUTH_CONTINUE_STORAGE_KEY);
    }
    return explicit;
  }
  return consumePaymentReturn() ?? consumeAuthContinue() ?? '/';
}

/** Guest-only routes (login/register). */
export function GuestRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return <ScreenLoader />;
  }
  if (status === 'authenticated') {
    return (
      <Navigate
        to={continueAfterAuth(
          (location.state as { from?: string } | null)?.from,
        )}
        replace
      />
    );
  }
  return <Outlet />;
}

/** Authenticated routes; redirect to onboarding when no workspaces. */
export function ProtectedRoute() {
  const { status, me } = useAuth();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return <ScreenLoader />;
  }
  if (status === 'unauthenticated') {
    rememberPaymentReturn(location);
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: internalReturnPath(location) }}
      />
    );
  }
  if (!me) {
    return <ScreenLoader />;
  }

  rememberPaymentReturn(location);

  const workspaces = me.workspaces;
  if (workspaces.length === 0 && location.pathname !== '/onboarding') {
    return (
      <Navigate
        to="/onboarding"
        replace
        state={{ from: internalReturnPath(location) }}
      />
    );
  }
  if (workspaces.length > 0 && location.pathname === '/onboarding') {
    return (
      <Navigate
        to={continueAfterAuth(
          (location.state as { from?: string } | null)?.from,
        )}
        replace
      />
    );
  }
  return <Outlet />;
}

/** Shell routes require a selected workspace. */
export function WorkspaceShellRoute() {
  const { status, me } = useAuth();
  const { currentWorkspace } = useWorkspace();
  const location = useLocation();

  if (status === 'authenticated' && me && me.workspaces.length > 0 && !currentWorkspace) {
    // WorkspaceProvider hydrates one paint after `me`; do not bounce to onboarding/home.
    return <ScreenLoader />;
  }
  if (!currentWorkspace) {
    return (
      <Navigate
        to="/onboarding"
        replace
        state={{ from: internalReturnPath(location) }}
      />
    );
  }
  return <Outlet />;
}

/** Permission-aware page guard. Unauthorized routes render a 403, not `/`. */
export function RequirePermission({
  permission,
  permissions,
}: {
  permission?: string;
  permissions?: readonly string[];
}) {
  const { ready, can, canAny } = usePermissions();
  if (!ready) {
    return <ScreenLoader />;
  }
  const needed = permissions ?? (permission ? [permission] : []);
  if (needed.length > 0 && !canAny(needed) && !(permission && can(permission))) {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}
