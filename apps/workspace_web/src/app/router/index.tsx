import { Navigate, Route, Routes } from 'react-router-dom';
import { WorkspaceLayout } from '@/app/layouts/workspace';
import { PlaceholderPage } from '@/components/shared/PlaceholderPage';
import { ChatStartPage } from '@/features/chat/pages/ChatStartPage';
import { OverviewPage } from '@/features/workspaces/pages/OverviewPage';

export function AppRouter() {
  return (
    <Routes>
      <Route element={<WorkspaceLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="chat" element={<ChatStartPage />} />
        <Route
          path="experts"
          element={<PlaceholderPage titleKey="nav.experts" />}
        />
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
        <Route
          path="members"
          element={<PlaceholderPage titleKey="nav.members" />}
        />
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
        <Route
          path="settings"
          element={<PlaceholderPage titleKey="nav.settings" />}
        />
        <Route
          path="*"
          element={<PlaceholderPage titleKey="errors.notFound" />}
        />
      </Route>
    </Routes>
  );
}
