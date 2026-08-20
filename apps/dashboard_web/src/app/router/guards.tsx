import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthProvider';
import { ScreenLoader } from '@/components/shared/ScreenLoader';

export function internalReturnPath(location: { pathname: string; search: string }): string {
  return `${location.pathname}${location.search}`;
}

export function GuestRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return <ScreenLoader />;
  }
  if (status === 'authenticated') {
    const from = (location.state as { from?: string } | null)?.from;
    const dest = from && from.startsWith('/') && !from.startsWith('//') ? from : '/';
    return <Navigate to={dest} replace />;
  }
  return <Outlet />;
}

/**
 * UX-only guard. Backend /api/platform/* remains authoritative.
 * Never treat a localStorage flag as authorization.
 */
export function RequirePlatformAdmin() {
  const { status, me } = useAuth();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return <ScreenLoader />;
  }
  if (status === 'unauthenticated') {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: internalReturnPath(location) }}
      />
    );
  }
  if (!me || !me.authorized || me.platform_role !== 'admin') {
    return (
      <Navigate to="/login" replace state={{ from: internalReturnPath(location) }} />
    );
  }
  return <Outlet />;
}
