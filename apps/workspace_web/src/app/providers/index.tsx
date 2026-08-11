import { Suspense, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter } from 'react-router-dom';
import { AppRouter } from '@/app/router';
import { ScreenLoader } from '@/components/shared/ScreenLoader';
import { Toaster } from '@/components/ui/sonner';
import { configureApiClient } from '@/services/api';
import { getAuthSession } from '@/services/auth/session';
import { getWorkspaceContext } from '@/services/auth/workspace-context';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

configureApiClient({
  baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  getAccessToken: () => getAuthSession().accessToken,
  getWorkspaceId: () => getWorkspaceContext().workspaceId,
  getWorkspaceSlug: () => getWorkspaceContext().workspaceSlug,
  onUnauthorized: () => {
    // Phase 1: redirect to login / clear session.
  },
});

export function AppProviders({ children }: { children?: ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      storageKey="geem-theme"
      enableSystem
      disableTransitionOnChange
      enableColorScheme
    >
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <Toaster />
            <Suspense fallback={<ScreenLoader />}>
              {children ?? <AppRouter />}
            </Suspense>
          </BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    </ThemeProvider>
  );
}
