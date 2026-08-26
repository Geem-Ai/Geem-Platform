import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { McpServer } from '@/services/api/mcp';
import { DeleteMcpServerDialog } from './DeleteMcpServerDialog';

const server: McpServer = {
  id: 'server-id',
  display_name: 'Figma',
  endpoint_host: 'mcp.figma.com',
  auth: { mode: 'oauth', strategy: 'dynamic_registration' },
  status: 'error',
  health: 'failed',
};

function renderDialog({
  isPending = false,
  errorMessage = null,
}: {
  isPending?: boolean;
  errorMessage?: string | null;
} = {}) {
  const onOpenChange = vi.fn();
  const onConfirm = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <DeleteMcpServerDialog
        server={server}
        open
        onOpenChange={onOpenChange}
        onConfirm={onConfirm}
        isPending={isPending}
        errorMessage={errorMessage}
      />
    </I18nextProvider>,
  );
  return { onOpenChange, onConfirm };
}

describe('DeleteMcpServerDialog', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('shows the selected server and destructive effects', () => {
    renderDialog();

    const dialog = screen.getByTestId('mcp-delete-dialog');
    expect(dialog).toHaveTextContent('Delete MCP server?');
    expect(dialog).toHaveTextContent('Figma');
    expect(dialog).toHaveTextContent('mcp.figma.com');
    expect(dialog).toHaveTextContent('Stored credentials and OAuth tokens');
    expect(dialog).toHaveTextContent('tool grants will be revoked');
  });

  it('cancels without confirming', () => {
    const { onOpenChange, onConfirm } = renderDialog();

    fireEvent.click(screen.getByTestId('mcp-delete-cancel'));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('keeps the dialog controlled while confirmation runs', () => {
    const { onOpenChange, onConfirm } = renderDialog({ isPending: true });

    expect(screen.getByTestId('mcp-delete-cancel')).toBeDisabled();
    expect(screen.getByTestId('mcp-delete-confirm')).toBeDisabled();
    expect(screen.getByTestId('mcp-delete-confirm')).toHaveTextContent(
      'Deleting server…',
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('renders a deletion error inside the dialog', () => {
    renderDialog({ errorMessage: 'The server could not be deleted.' });

    expect(screen.getByRole('alert')).toHaveTextContent(
      'The server could not be deleted.',
    );
  });
});
