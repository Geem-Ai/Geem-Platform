import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminLayout } from '@/app/layouts/admin';
import { GuestRoute, RequirePlatformAdmin } from '@/app/router/guards';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { ComingSoonPage } from '@/features/overview/pages/ComingSoonPage';
import { OverviewPage } from '@/features/overview/pages/OverviewPage';

export function AppRouter() {
  return (
    <Routes>
      <Route element={<GuestRoute />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>

      <Route element={<RequirePlatformAdmin />}>
        <Route element={<AdminLayout />}>
          <Route index element={<OverviewPage />} />
          <Route
            path="workspaces"
            element={<ComingSoonPage titleKey="nav.workspaces" phase="12B" />}
          />
          <Route path="users" element={<ComingSoonPage titleKey="nav.users" phase="12B" />} />
          <Route
            path="experts"
            element={<ComingSoonPage titleKey="nav.platformExperts" phase="12D" />}
          />
          <Route path="usage" element={<ComingSoonPage titleKey="nav.usage" phase="12G" />} />
          <Route path="plans" element={<ComingSoonPage titleKey="nav.plans" phase="12C" />} />
          <Route path="credits" element={<ComingSoonPage titleKey="nav.credits" phase="12C" />} />
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
