import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthProvider';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ScreenLoader } from '@/components/shared/ScreenLoader';

/** Guest-only routes (login/register). */
export function GuestRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return <ScreenLoader />;
  }
  if (status === 'authenticated') {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from || '/'} replace />;
  }
  return <Outlet />;
}

/** Authenticated routes; redirect to onboarding when no workspaces. */
export function ProtectedRoute() {
  const { status } = useAuth();
  const { availableWorkspaces } = useWorkspace();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return <ScreenLoader />;
  }
  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (availableWorkspaces.length === 0 && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />;
  }
  if (availableWorkspaces.length > 0 && location.pathname === '/onboarding') {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

/** Shell routes require a selected workspace. */
export function WorkspaceShellRoute() {
  const { currentWorkspace } = useWorkspace();
  if (!currentWorkspace) {
    return <Navigate to="/onboarding" replace />;
  }
  return <Outlet />;
}
