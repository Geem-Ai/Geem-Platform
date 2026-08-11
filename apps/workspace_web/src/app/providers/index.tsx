import { Suspense, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter } from 'react-router-dom';
import { AppRouter } from '@/app/router';
import { DirectionProvider } from '@/app/providers/direction-provider';
import { ScreenLoader } from '@/components/shared/ScreenLoader';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { WorkspaceProvider } from '@/features/workspaces/WorkspaceProvider';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
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
            <DirectionProvider>
              <AuthProvider>
                <WorkspaceProvider>
                  <Toaster />
                  <Suspense fallback={<ScreenLoader />}>
                    {children ?? <AppRouter />}
                  </Suspense>
                </WorkspaceProvider>
              </AuthProvider>
            </DirectionProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    </ThemeProvider>
  );
}
