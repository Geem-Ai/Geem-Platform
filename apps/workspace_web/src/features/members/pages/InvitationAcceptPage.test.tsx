import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { InvitationAcceptPage } from './InvitationAcceptPage';

const authState: {
  status: 'bootstrapping' | 'authenticated' | 'unauthenticated';
  user: { id: string; email: string } | null;
} = {
  status: 'unauthenticated',
  user: null,
};

const logout = vi.fn();
const reloadMe = vi.fn();
const selectWorkspace = vi.fn();
const refreshWorkspaces = vi.fn();
const acceptWorkspaceInvitation = vi.fn();
const setWorkspaceContext = vi.fn();
const saveWorkspacePreference = vi.fn();

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', setTheme: vi.fn() }),
}));

vi.mock('@/features/auth/AuthProvider', () => ({
  useAuth: () => ({
    status: authState.status,
    user: authState.user,
    logout,
    reloadMe,
  }),
}));

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    selectWorkspace,
    refreshWorkspaces,
  }),
}));

vi.mock('@/services/api/invitations', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/invitations')>(
    '@/services/api/invitations',
  );
  return {
    ...actual,
    acceptWorkspaceInvitation: (...args: unknown[]) => acceptWorkspaceInvitation(...args),
  };
});

vi.mock('@/services/auth/workspace-context', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/auth/workspace-context')
  >('@/services/auth/workspace-context');
  return {
    ...actual,
    setWorkspaceContext: (...args: unknown[]) => setWorkspaceContext(...args),
    saveWorkspacePreference: (...args: unknown[]) => saveWorkspacePreference(...args),
  };
});

function renderAccept(search = '?token=invite-token') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/invitations/accept${search}`]}>
          <Routes>
            <Route path="/invitations/accept" element={<InvitationAcceptPage />} />
            <Route path="/members" element={<div>members-home</div>} />
            <Route path="/login" element={<div>login-page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe('InvitationAcceptPage', () => {
  beforeEach(async () => {
    authState.status = 'unauthenticated';
    authState.user = null;
    logout.mockReset();
    reloadMe.mockReset();
    selectWorkspace.mockReset();
    refreshWorkspaces.mockReset();
    acceptWorkspaceInvitation.mockReset();
    setWorkspaceContext.mockReset();
    saveWorkspacePreference.mockReset();
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('guides unauthenticated visitors to login and register', async () => {
    renderAccept();
    expect(await screen.findByTestId('invitation-accept-guest')).toBeInTheDocument();
    expect(screen.getByTestId('invitation-login')).toBeInTheDocument();
    expect(screen.getByTestId('invitation-register')).toBeInTheDocument();
    expect(acceptWorkspaceInvitation).not.toHaveBeenCalled();
  });

  it('renders Arabic guest copy under RTL', async () => {
    await i18n.changeLanguage('ar');
    renderAccept();
    expect(await screen.findByTestId('invitation-accept-guest')).toHaveTextContent(
      i18n.t('invitations.signInToContinue'),
    );
    expect(document.documentElement.dir).toBe('rtl');
  });

  it('shows a safe invalid state without a token', async () => {
    renderAccept('');
    expect(await screen.findByTestId('invitation-invalid')).toBeInTheDocument();
  });

  it('accepts an authenticated invitation and leaves the token URL', async () => {
    authState.status = 'authenticated';
    authState.user = { id: 'u2', email: 'new@example.com' };
    acceptWorkspaceInvitation.mockResolvedValue({
      invitation_id: 'inv-1',
      workspace_id: 'ws-a',
      workspace_name: 'Acme',
      workspace_slug: 'acme',
      role: 'member',
      membership_id: 'mem-2',
      already_member: false,
    });
    reloadMe.mockImplementation(async () => {
      expect(setWorkspaceContext).toHaveBeenCalledWith(
        expect.objectContaining({ workspaceId: 'ws-a' }),
      );
      return {
        user: authState.user,
        workspaces: [
          { id: 'ws-old', name: 'Prior', slug: 'prior', role: 'owner' },
          { id: 'ws-a', name: 'Acme', slug: 'acme', role: 'member' },
        ],
        current_workspace: { id: 'ws-a', name: 'Acme', slug: 'acme', role: 'member' },
      };
    });
    refreshWorkspaces.mockResolvedValue(undefined);
    renderAccept();
    await waitFor(() => {
      expect(acceptWorkspaceInvitation).toHaveBeenCalledWith('invite-token');
    });
    expect(await screen.findByText('members-home')).toBeInTheDocument();
    expect(saveWorkspacePreference).toHaveBeenCalledWith('u2', 'ws-a');
    expect(selectWorkspace).toHaveBeenCalledWith(
      'ws-a',
      expect.objectContaining({
        id: 'ws-a',
        name: 'Acme',
        slug: 'acme',
        role: 'member',
      }),
    );
  });

  it('treats idempotent already-member acceptance as success', async () => {
    authState.status = 'authenticated';
    authState.user = { id: 'u2', email: 'new@example.com' };
    acceptWorkspaceInvitation.mockResolvedValue({
      invitation_id: 'inv-1',
      workspace_id: 'ws-a',
      workspace_name: 'Acme',
      workspace_slug: 'acme',
      role: 'member',
      membership_id: 'mem-2',
      already_member: true,
    });
    reloadMe.mockResolvedValue({
      user: authState.user,
      workspaces: [{ id: 'ws-a', name: 'Acme', slug: 'acme', role: 'member' }],
      current_workspace: { id: 'ws-a', name: 'Acme', slug: 'acme', role: 'member' },
    });
    refreshWorkspaces.mockResolvedValue(undefined);
    renderAccept();
    await waitFor(() => {
      expect(acceptWorkspaceInvitation).toHaveBeenCalledWith('invite-token');
    });
    expect(await screen.findByText('members-home')).toBeInTheDocument();
  });

  it('renders expired, revoked, mismatch, and already-accepted states', async () => {
    const { ApiError } = await import('@/services/api/errors');
    authState.status = 'authenticated';
    authState.user = { id: 'u2', email: 'bob@example.com' };

    acceptWorkspaceInvitation.mockRejectedValue(
      new ApiError('gone', { status: 410, code: 'invitation_expired' }),
    );
    const first = renderAccept();
    expect(await screen.findByTestId('invitation-expired')).toBeInTheDocument();
    first.unmount();

    acceptWorkspaceInvitation.mockRejectedValue(
      new ApiError('conflict', { status: 409, code: 'invitation_revoked' }),
    );
    const second = renderAccept();
    expect(await screen.findByTestId('invitation-revoked')).toBeInTheDocument();
    second.unmount();

    acceptWorkspaceInvitation.mockRejectedValue(
      new ApiError('forbidden', { status: 403, code: 'invitation_email_mismatch' }),
    );
    const third = renderAccept();
    expect(await screen.findByTestId('invitation-mismatch')).toBeInTheDocument();
    third.unmount();

    acceptWorkspaceInvitation.mockRejectedValue(
      new ApiError('conflict', { status: 409, code: 'invitation_already_accepted' }),
    );
    renderAccept();
    expect(await screen.findByTestId('invitation-already')).toBeInTheDocument();
  });
});
