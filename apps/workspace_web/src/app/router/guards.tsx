import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthProvider';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ScreenLoader } from '@/components/shared/ScreenLoader';

const PAYMENT_RETURN_STORAGE_KEY = 'geem.billing.paymentReturn';

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

/** Login/onboarding continue target. Prefers `from`, then stashed payment return. */
export function continueAfterAuth(from: unknown): string {
  const explicit = safeInternalPath(from);
  if (
    explicit &&
    explicit !== '/login' &&
    explicit !== '/register' &&
    explicit !== '/onboarding'
  ) {
    if (isBillingPaymentResultPath(explicit.split('?')[0] ?? explicit)) {
      consumePaymentReturn();
    }
    return explicit;
  }
  return consumePaymentReturn() ?? '/';
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
