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
import { MembersPage } from '@/features/members/pages/MembersPage';
import { CreateWorkspacePage } from '@/features/workspaces/pages/CreateWorkspacePage';
import { OnboardingPage } from '@/features/workspaces/pages/OnboardingPage';
import { OverviewPage } from '@/features/workspaces/pages/OverviewPage';
import { SettingsPage } from '@/features/workspaces/pages/SettingsPage';

export function AppRouter() {
  return (
    <Routes>
      <Route element={<GuestRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/workspaces/new" element={<CreateWorkspacePage />} />

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
            <Route
              path="api/keys"
              element={<PlaceholderPage titleKey="nav.apiKeys" />}
            />
            <Route
              path="api/usage"
              element={<PlaceholderPage titleKey="nav.usage" />}
            />
            <Route path="apps" element={<PlaceholderPage titleKey="nav.apps" />} />
            <Route path="members" element={<MembersPage />} />
            <Route
              path="storage"
              element={<PlaceholderPage titleKey="nav.storage" />}
            />
            <Route
              path="billing"
              element={<Navigate to="/billing/subscription" replace />}
            />
            <Route
              path="billing/subscription"
              element={<PlaceholderPage titleKey="nav.subscription" />}
            />
            <Route
              path="billing/usage"
              element={<PlaceholderPage titleKey="nav.usage" />}
            />
            <Route
              path="billing/credits"
              element={<PlaceholderPage titleKey="nav.credits" />}
            />
            <Route
              path="billing/history"
              element={<PlaceholderPage titleKey="nav.billingHistory" />}
            />
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
