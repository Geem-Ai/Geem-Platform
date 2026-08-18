import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { MembersPage } from './MembersPage';
import { queryKeys } from '@/services/api/query-keys';

const workspaceState = { id: 'ws-a', role: 'owner' as string };
const authState = { id: 'u-owner', email: 'owner@example.com' };

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: {
      id: workspaceState.id,
      name: 'Acme',
      slug: 'acme',
      role: workspaceState.role,
    },
    currentMembership: {
      id: 'm1',
      workspace_id: workspaceState.id,
      user_id: authState.id,
      role: workspaceState.role,
      created_at: '2026-01-01T00:00:00Z',
    },
  }),
}));

vi.mock('@/features/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { id: authState.id, email: authState.email, status: 'active', platform_role: 'none' },
  }),
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

const listMembers = vi.fn();
const listWorkspaceInvitations = vi.fn();
const createWorkspaceInvitation = vi.fn();
const resendWorkspaceInvitation = vi.fn();
const revokeWorkspaceInvitation = vi.fn();
const updateMemberRole = vi.fn();
const removeMember = vi.fn();

vi.mock('@/services/api/workspaces', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/workspaces')>(
    '@/services/api/workspaces',
  );
  return {
    ...actual,
    listMembers: (...args: unknown[]) => listMembers(...args),
    updateMemberRole: (...args: unknown[]) => updateMemberRole(...args),
    removeMember: (...args: unknown[]) => removeMember(...args),
  };
});

vi.mock('@/services/api/invitations', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/invitations')>(
    '@/services/api/invitations',
  );
  return {
    ...actual,
    listWorkspaceInvitations: (...args: unknown[]) => listWorkspaceInvitations(...args),
    createWorkspaceInvitation: (...args: unknown[]) => createWorkspaceInvitation(...args),
    resendWorkspaceInvitation: (...args: unknown[]) => resendWorkspaceInvitation(...args),
    revokeWorkspaceInvitation: (...args: unknown[]) => revokeWorkspaceInvitation(...args),
  };
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <MembersPage />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe('MembersPage', () => {
  beforeEach(async () => {
    workspaceState.role = 'owner';
    listMembers.mockReset();
    listWorkspaceInvitations.mockReset();
    createWorkspaceInvitation.mockReset();
    resendWorkspaceInvitation.mockReset();
    revokeWorkspaceInvitation.mockReset();
    listMembers.mockResolvedValue([
      {
        id: 'mem-1',
        user_id: 'u-owner',
        email: 'owner@example.com',
        role: 'owner',
        created_at: '2026-01-01T00:00:00Z',
      },
    ]);
    listWorkspaceInvitations.mockResolvedValue({
      items: [
        {
          id: 'inv-1',
          workspace_id: 'ws-a',
          email: 'new@example.com',
          role: 'member',
          status: 'pending',
          expires_at: '2026-08-21T12:00:00Z',
          created_at: '2026-08-18T12:00:00Z',
          invited_by: { id: 'u-owner', email: 'owner@example.com' },
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('lets the owner invite and shows pending invitations', async () => {
    renderPage();
    expect(await screen.findByTestId('invite-member-button')).toBeInTheDocument();
    expect(await screen.findByText('owner@example.com')).toBeInTheDocument();
    expect(await screen.findByText('new@example.com')).toBeInTheDocument();
    expect(screen.getByTestId('role-matrix')).toBeInTheDocument();
    expect(screen.getByTestId('role-badge-owner')).toBeInTheDocument();
    expect(screen.getByText('1 person')).toBeInTheDocument();
    expect(queryKeys.invitations('ws-a')[1]).toBe('ws-a');
  });

  it('lets an admin invite', async () => {
    workspaceState.role = 'admin';
    renderPage();
    expect(await screen.findByTestId('invite-member-button')).toBeInTheDocument();
    expect(await screen.findByTestId('pending-invitations')).toBeInTheDocument();
  });

  it('hides invite and pending management for members', async () => {
    workspaceState.role = 'member';
    renderPage();
    expect(await screen.findByText('owner@example.com')).toBeInTheDocument();
    expect(screen.queryByTestId('invite-member-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pending-invitations')).not.toBeInTheDocument();
    expect(screen.getByTestId('role-matrix')).toBeInTheDocument();
  });

  it('validates email and does not offer owner as an invite role', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('invite-member-button'));
    fireEvent.click(screen.getByTestId('invite-submit'));
    expect(await screen.findByTestId('invite-error')).toBeInTheDocument();
    expect(screen.getByTestId('invite-role-admin')).toBeInTheDocument();
    expect(screen.getByTestId('invite-role-member')).toBeInTheDocument();
    expect(screen.queryByTestId('invite-role-owner')).not.toBeInTheDocument();
  });

  it('sends an admin invite and shows typed already-member errors', async () => {
    const { ApiError } = await import('@/services/api/errors');
    createWorkspaceInvitation.mockRejectedValueOnce(
      new ApiError('conflict', { status: 409, code: 'already_workspace_member' }),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId('invite-member-button'));
    fireEvent.change(screen.getByTestId('invite-email'), {
      target: { value: 'already@example.com' },
    });
    fireEvent.click(screen.getByTestId('invite-role-admin'));
    fireEvent.click(screen.getByTestId('invite-submit'));
    expect(await screen.findByTestId('invite-error')).toHaveTextContent(
      i18n.t('members.errors.alreadyMember'),
    );

    createWorkspaceInvitation.mockResolvedValueOnce({
      id: 'inv-2',
      workspace_id: 'ws-a',
      email: 'ok@example.com',
      role: 'admin',
      status: 'pending',
      expires_at: '2026-08-21T12:00:00Z',
      created_at: '2026-08-18T12:00:00Z',
      invited_by: { id: 'u-owner', email: 'owner@example.com' },
    });
    fireEvent.change(screen.getByTestId('invite-email'), {
      target: { value: 'ok@example.com' },
    });
    fireEvent.click(screen.getByTestId('invite-submit'));
    await waitFor(() => {
      expect(createWorkspaceInvitation).toHaveBeenCalledWith('ws-a', {
        email: 'ok@example.com',
        role: 'admin',
      });
    });
  });

  it('shows a typed error when a pending invitation already exists', async () => {
    const { ApiError } = await import('@/services/api/errors');
    createWorkspaceInvitation.mockRejectedValueOnce(
      new ApiError('conflict', { status: 409, code: 'invitation_already_exists' }),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId('invite-member-button'));
    fireEvent.change(screen.getByTestId('invite-email'), {
      target: { value: 'new@example.com' },
    });
    fireEvent.click(screen.getByTestId('invite-submit'));
    expect(await screen.findByTestId('invite-error')).toHaveTextContent(
      i18n.t('members.errors.alreadyInvited'),
    );
  });

  it('resends and revokes pending invitations', async () => {
    resendWorkspaceInvitation.mockResolvedValue({
      id: 'inv-1',
      workspace_id: 'ws-a',
      email: 'new@example.com',
      role: 'member',
      status: 'pending',
      expires_at: '2026-08-22T12:00:00Z',
      created_at: '2026-08-18T12:00:00Z',
      invited_by: { id: 'u-owner', email: 'owner@example.com' },
    });
    revokeWorkspaceInvitation.mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByTestId('resend-invitation'));
    await waitFor(() => {
      expect(resendWorkspaceInvitation).toHaveBeenCalledWith('ws-a', 'inv-1');
    });
    fireEvent.click(screen.getByTestId('revoke-invitation'));
    fireEvent.click(await screen.findByTestId('confirm-revoke-invitation'));
    await waitFor(() => {
      expect(revokeWorkspaceInvitation).toHaveBeenCalledWith('ws-a', 'inv-1');
    });
  });

  it('renders Arabic role matrix labels', async () => {
    await i18n.changeLanguage('ar');
    renderPage();
    expect(await screen.findByTestId('role-matrix')).toHaveTextContent(
      i18n.t('members.matrix.manageMembers'),
    );
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByRole('heading', { name: 'الأعضاء' })).toBeInTheDocument();
  });
});
