import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminLayout } from '@/app/layouts/admin';
import { GuestRoute, RequirePlatformAdmin } from '@/app/router/guards';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { ComingSoonPage } from '@/features/overview/pages/ComingSoonPage';
import { OverviewPage } from '@/features/overview/pages/OverviewPage';
import { CreditsPage } from '@/features/credits/pages/CreditsPage';
import { CreditDetailPage } from '@/features/credits/pages/CreditDetailPage';
import { PlansPage } from '@/features/plans/pages/PlansPage';
import { PlanCreatePage } from '@/features/plans/pages/PlanCreatePage';
import { PlanDetailPage } from '@/features/plans/pages/PlanDetailPage';
import { UsersPage } from '@/features/users/pages/UsersPage';
import { UserDetailPage } from '@/features/users/pages/UserDetailPage';
import { WorkspacesPage } from '@/features/workspaces/pages/WorkspacesPage';
import { WorkspaceDetailPage } from '@/features/workspaces/pages/WorkspaceDetailPage';

export function AppRouter() {
  return (
    <Routes>
      <Route element={<GuestRoute />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>

      <Route element={<RequirePlatformAdmin />}>
        <Route element={<AdminLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="workspaces" element={<WorkspacesPage />} />
          <Route path="workspaces/:workspaceId" element={<WorkspaceDetailPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="users/:userId" element={<UserDetailPage />} />
          <Route
            path="experts"
            element={<ComingSoonPage titleKey="nav.platformExperts" phase="12D" />}
          />
          <Route path="usage" element={<ComingSoonPage titleKey="nav.usage" phase="12G" />} />
          <Route path="plans" element={<PlansPage />} />
          <Route path="plans/new" element={<PlanCreatePage />} />
          <Route path="plans/:planId" element={<PlanDetailPage />} />
          <Route path="credits" element={<CreditsPage />} />
          <Route path="credits/:workspaceId" element={<CreditDetailPage />} />
          <Route
            path="app-store"
            element={<ComingSoonPage titleKey="nav.appStore" phase="12E" />}
          />
          <Route
            path="purchases"
            element={<ComingSoonPage titleKey="nav.purchases" phase="12F" />}
          />
          <Route
            path="payment-gateways"
            element={<ComingSoonPage titleKey="nav.paymentGateways" phase="12F" />}
          />
          <Route
            path="audit-logs"
            element={<ComingSoonPage titleKey="nav.auditLogs" phase="12G" />}
          />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
