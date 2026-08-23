import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminLayout } from '@/app/layouts/admin';
import { GuestRoute, RequirePlatformAdmin } from '@/app/router/guards';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { ExpertsPage } from '@/features/experts/pages/ExpertsPage';
import { ExpertCreatePage } from '@/features/experts/pages/ExpertCreatePage';
import { ExpertDetailPage } from '@/features/experts/pages/ExpertDetailPage';
import { ComingSoonPage } from '@/features/overview/pages/ComingSoonPage';
import { PaymentGatewaysPage } from '@/features/payment-gateways/pages/PaymentGatewaysPage';
import { PurchasesPage } from '@/features/purchases/pages/PurchasesPage';
import { PurchaseDetailPage } from '@/features/purchases/pages/PurchaseDetailPage';
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
import { AppStorePage } from '@/features/app-store/pages/AppStorePage';
import { AppCreatePage } from '@/features/app-store/pages/AppCreatePage';
import { AppDetailPage } from '@/features/app-store/pages/AppDetailPage';

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
          <Route path="experts" element={<ExpertsPage />} />
          <Route path="experts/new" element={<ExpertCreatePage />} />
          <Route path="experts/:expertId" element={<ExpertDetailPage />} />
          <Route path="usage" element={<ComingSoonPage titleKey="nav.usage" phase="12G" />} />
          <Route path="plans" element={<PlansPage />} />
          <Route path="plans/new" element={<PlanCreatePage />} />
          <Route path="plans/:planId" element={<PlanDetailPage />} />
          <Route path="credits" element={<CreditsPage />} />
          <Route path="credits/:workspaceId" element={<CreditDetailPage />} />
          <Route path="app-store" element={<AppStorePage />} />
          <Route path="app-store/new" element={<AppCreatePage />} />
          <Route path="app-store/:appId" element={<AppDetailPage />} />
          <Route path="purchases" element={<PurchasesPage />} />
          <Route path="purchases/:purchaseId" element={<PurchaseDetailPage />} />
          <Route path="payment-gateways" element={<PaymentGatewaysPage />} />
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
