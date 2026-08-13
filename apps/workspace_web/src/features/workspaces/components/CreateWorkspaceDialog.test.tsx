import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ApiError } from '@/services/api/errors';
import { CreateWorkspaceDialog } from './CreateWorkspaceDialog';

const createWorkspace = vi.fn();
const onOpenChange = vi.fn();

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    createWorkspace,
  }),
}));

function renderDialog(open = true) {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <CreateWorkspaceDialog open={open} onOpenChange={onOpenChange} />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe('CreateWorkspaceDialog', () => {
  beforeEach(async () => {
    createWorkspace.mockReset();
    onOpenChange.mockReset();
    createWorkspace.mockResolvedValue({
      id: 'ws-new',
      name: 'Acme Research',
      slug: 'acme-research',
      status: 'active',
      role: 'owner',
    });
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('suggests a slug from the workspace name', async () => {
    renderDialog();
    await screen.findByTestId('create-workspace-dialog');
    fireEvent.change(screen.getByTestId('create-workspace-name'), {
      target: { value: 'Acme Research' },
    });
    expect(screen.getByTestId('create-workspace-slug')).toHaveValue(
      'acme-research',
    );
    expect(screen.getByTestId('workspace-slug-suffix').textContent).toMatch(
      /^\./,
    );
  });

  it('creates a workspace and closes the dialog', async () => {
    renderDialog();
    await screen.findByTestId('create-workspace-dialog');
    fireEvent.change(screen.getByTestId('create-workspace-name'), {
      target: { value: 'Acme Research' },
    });
    fireEvent.click(screen.getByTestId('create-workspace-submit'));
    await waitFor(() => {
      expect(createWorkspace).toHaveBeenCalledWith({
        name: 'Acme Research',
        slug: 'acme-research',
      });
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows an API error without closing', async () => {
    createWorkspace.mockRejectedValueOnce(
      new ApiError('taken', { status: 409, code: 'workspace_slug_taken' }),
    );
    renderDialog();
    await screen.findByTestId('create-workspace-dialog');
    fireEvent.change(screen.getByTestId('create-workspace-name'), {
      target: { value: 'Acme' },
    });
    fireEvent.click(screen.getByTestId('create-workspace-submit'));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
