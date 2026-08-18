import { Navigate, Route, Routes } from 'react-router-dom';
import { WorkspaceLayout } from '@/app/layouts/workspace';
import {
  GuestRoute,
  ProtectedRoute,
  WorkspaceShellRoute,
} from '@/app/router/guards';
import { PlaceholderPage } from '@/components/shared/PlaceholderPage';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { RegisterPage } from '@/features/auth/pages/RegisterPage';
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

export function AppRouter() {
  return (
    <Routes>
      <Route path="/invitations/accept" element={<InvitationAcceptPage />} />

      <Route element={<GuestRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/workspaces/new" element={<Navigate to="/" replace />} />

        <Route element={<WorkspaceShellRoute />}>
          <Route element={<WorkspaceLayout />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={<ChatStartPage />} />
            <Route path="chat/:conversationId" element={<ChatPage />} />
            <Route path="overview" element={<OverviewPage />} />
            {/* Experts list hosts Metronic-style create/edit/view Sheets */}
            <Route path="experts" element={<ExpertsPage />} />
            <Route path="experts/new" element={<ExpertsPage />} />
            <Route path="experts/:expertId/edit" element={<ExpertsPage />} />
            <Route path="experts/:expertId" element={<ExpertsPage />} />
            <Route path="api" element={<Navigate to="/api/keys" replace />} />
            <Route path="api/keys" element={<ApiKeysPage />} />
            <Route path="api/usage" element={<ApiUsagePage />} />
            <Route path="apps" element={<AppsPage />} />
            <Route path="apps/installed" element={<InstalledAppsPage />} />
            <Route path="apps/payment/result" element={<AppPaymentResultPage />} />
            <Route path="apps/:slug" element={<AppsPage />} />
            <Route path="members" element={<MembersPage />} />
            <Route path="storage" element={<StoragePage />} />
            <Route
              path="billing"
              element={<Navigate to="/billing/subscription" replace />}
            />
            <Route path="billing/subscription" element={<SubscriptionPage />} />
            <Route path="billing/usage" element={<UsagePage />} />
            <Route path="billing/usage/history" element={<UsageHistoryPage />} />
            <Route path="billing/credits" element={<CreditsPage />} />
            <Route path="billing/history" element={<BillingHistoryPage />} />
            <Route path="billing/payment/success" element={<PaymentResultPage />} />
            <Route path="billing/payment/failed" element={<PaymentResultPage />} />
            <Route path="billing/payment/pending" element={<PaymentResultPage />} />
            <Route path="billing/payment/result" element={<PaymentResultPage />} />
            <Route path="settings" element={<SettingsPage />} />
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
