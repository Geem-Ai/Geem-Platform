import { Navigate, Route, Routes } from 'react-router-dom';
import { WorkspaceLayout } from '@/app/layouts/workspace';
import {
  GuestRoute,
  ProtectedRoute,
  RequirePermission,
  WorkspaceShellRoute,
} from '@/app/router/guards';
import { PlaceholderPage } from '@/components/shared/PlaceholderPage';
import { ScreenLoader } from '@/components/shared/ScreenLoader';
import { ForbiddenPage } from '@/features/authz/pages/ForbiddenPage';
import { WorkspacePermission } from '@/features/authz/permissions';
import { firstAllowedNavPath } from '@/features/authz/filter-nav';
import { usePermissions } from '@/features/authz/usePermissions';
import { workspaceNav } from '@/app/layouts/workspace/nav-config';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { RegisterPage } from '@/features/auth/pages/RegisterPage';
import { ForgotPasswordPage } from '@/features/auth/pages/ForgotPasswordPage';
import { ResetPasswordPage } from '@/features/auth/pages/ResetPasswordPage';
import { AccountPage } from '@/features/settings/pages/AccountPage';
import { ChatPage } from '@/features/chat/pages/ChatPage';
import { ChatStartPage } from '@/features/chat/pages/ChatStartPage';
import { ExpertsPage } from '@/features/experts/pages/ExpertsPage';
import { InvitationAcceptPage } from '@/features/members/pages/InvitationAcceptPage';
import { MembersPage } from '@/features/members/pages/MembersPage';
import { OnboardingPage } from '@/features/workspaces/pages/OnboardingPage';
import { OverviewPage } from '@/features/workspaces/pages/OverviewPage';
import { SettingsPage } from '@/features/workspaces/pages/SettingsPage';
import { BillingHistoryPage } from '@/features/billing/pages/BillingHistoryPage';
import { CreditsPage } from '@/features/billing/pages/CreditsPage';
import { PaymentResultPage } from '@/features/billing/pages/PaymentResultPage';
import { SubscriptionPage } from '@/features/billing/pages/SubscriptionPage';
import { ApiKeysPage } from '@/features/api-keys/pages/ApiKeysPage';
import { ApiUsagePage } from '@/features/api-keys/pages/ApiUsagePage';
import { UsageHistoryPage } from '@/features/usage/pages/UsageHistoryPage';
import { UsagePage } from '@/features/usage/pages/UsagePage';
import { StoragePage } from '@/features/storage/pages/StoragePage';
import { AppsPage } from '@/features/apps/pages/AppsPage';
import { AppPaymentResultPage } from '@/features/apps/pages/AppPaymentResultPage';
import { InstalledAppsPage } from '@/features/apps/pages/InstalledAppsPage';

function HomeRedirect() {
  const { ready, can, permissions } = usePermissions();
  if (!ready) return <ScreenLoader />;
  if (can(WorkspacePermission.CHAT_USE)) {
    return <Navigate to="/chat" replace />;
  }
  if (can(WorkspacePermission.WORKSPACE_VIEW)) {
    return <Navigate to="/overview" replace />;
  }
  const first = firstAllowedNavPath(workspaceNav, permissions);
  if (first) return <Navigate to={first} replace />;
  return <ForbiddenPage />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/invitations/accept" element={<InvitationAcceptPage />} />

      <Route element={<GuestRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/workspaces/new" element={<Navigate to="/" replace />} />

        <Route element={<WorkspaceShellRoute />}>
          <Route element={<WorkspaceLayout />}>
            <Route index element={<HomeRedirect />} />
            <Route
              element={
                <RequirePermission permission={WorkspacePermission.CHAT_USE} />
              }
            >
              <Route path="chat" element={<ChatStartPage />} />
              <Route path="chat/:conversationId" element={<ChatPage />} />
            </Route>
            <Route
              element={
                <RequirePermission
                  permission={WorkspacePermission.WORKSPACE_VIEW}
                />
              }
            >
              <Route path="overview" element={<OverviewPage />} />
            </Route>
            <Route
              element={
                <RequirePermission permission={WorkspacePermission.EXPERTS_VIEW} />
              }
            >
              <Route path="experts" element={<ExpertsPage />} />
              <Route path="experts/new" element={<ExpertsPage />} />
              <Route path="experts/:expertId/edit" element={<ExpertsPage />} />
              <Route path="experts/:expertId" element={<ExpertsPage />} />
            </Route>
            <Route
              element={
                <RequirePermission permission={WorkspacePermission.API_KEYS_VIEW} />
              }
            >
              <Route path="api" element={<Navigate to="/api/keys" replace />} />
              <Route path="api/keys" element={<ApiKeysPage />} />
            </Route>
            <Route
              element={
                <RequirePermission
                  permission={WorkspacePermission.API_USAGE_VIEW}
                />
              }
            >
              <Route path="api/usage" element={<ApiUsagePage />} />
            </Route>
            <Route
              element={
                <RequirePermission permission={WorkspacePermission.APPS_VIEW} />
              }
            >
              <Route path="apps" element={<AppsPage />} />
              <Route path="apps/installed" element={<InstalledAppsPage />} />
              <Route path="apps/payment/result" element={<AppPaymentResultPage />} />
              <Route path="apps/:slug" element={<AppsPage />} />
            </Route>
            <Route
              element={
                <RequirePermission permission={WorkspacePermission.MEMBERS_VIEW} />
              }
            >
              <Route path="members" element={<MembersPage />} />
            </Route>
            <Route
              element={
                <RequirePermission permission={WorkspacePermission.STORAGE_VIEW} />
              }
            >
              <Route path="storage" element={<StoragePage />} />
            </Route>
            <Route
              element={
                <RequirePermission permission={WorkspacePermission.BILLING_VIEW} />
              }
            >
              <Route
                path="billing"
                element={<Navigate to="/billing/subscription" replace />}
              />
              <Route path="billing/subscription" element={<SubscriptionPage />} />
              <Route path="billing/usage" element={<UsagePage />} />
              <Route path="billing/usage/history" element={<UsageHistoryPage />} />
              <Route path="billing/credits" element={<CreditsPage />} />
              <Route path="billing/history" element={<BillingHistoryPage />} />
            </Route>
            <Route path="billing/payment/success" element={<PaymentResultPage />} />
            <Route path="billing/payment/failed" element={<PaymentResultPage />} />
            <Route path="billing/payment/pending" element={<PaymentResultPage />} />
            <Route path="billing/payment/result" element={<PaymentResultPage />} />
            <Route
              element={
                <RequirePermission
                  permission={WorkspacePermission.WORKSPACE_SETTINGS_VIEW}
                />
              }
            >
              <Route path="settings" element={<SettingsPage />} />
            </Route>
            <Route path="account" element={<AccountPage />} />
            <Route
              path="*"
              element={<PlaceholderPage titleKey="errors.notFound" />}
            />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
