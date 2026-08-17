import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/lib/i18n';
import { ChatComposer } from './ChatComposer';

const uploadChatAttachment = vi.fn();
const deleteChatAttachment = vi.fn();

vi.mock('@/services/api', async () => {
  const actual = await vi.importActual<typeof import('@/services/api')>('@/services/api');
  return {
    ...actual,
    CHAT_ATTACHMENT_MAX_BYTES: 5 * 1024 * 1024,
    CHAT_ATTACHMENT_MAX_MB: 5,
    uploadChatAttachment: (...args: unknown[]) => uploadChatAttachment(...args),
    deleteChatAttachment: (...args: unknown[]) => deleteChatAttachment(...args),
  };
});

function withI18n(ui: React.ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe('ChatComposer attachment upload', () => {
  beforeEach(() => {
    uploadChatAttachment.mockReset();
    deleteChatAttachment.mockReset();
    deleteChatAttachment.mockResolvedValue(undefined);
  });

  it('opens attach menu with Images / PDF / Text', async () => {
    withI18n(<ChatComposer onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByTestId('chat-attach-button'));
    expect(await screen.findByTestId('chat-attach-images')).toBeInTheDocument();
    expect(screen.getByTestId('chat-attach-pdf')).toBeInTheDocument();
    expect(screen.getByTestId('chat-attach-text')).toBeInTheDocument();
  });

  it('sets PDF accept then uploads a file, shows progress, and deletes on dismiss', async () => {
    uploadChatAttachment.mockImplementation(
      async (
        _file: File,
        options?: { onProgress?: (n: number) => void },
      ) => {
        options?.onProgress?.(40);
        options?.onProgress?.(100);
        return {
          id: 'att-1',
          original_filename: 'brief.pdf',
          mime_type: 'application/pdf',
          byte_size: 12,
          sha256: 'abc',
          created_at: '2026-01-01T00:00:00Z',
          expires_at: '2026-01-01T12:00:00Z',
        };
      },
    );

    withI18n(<ChatComposer onSubmit={vi.fn()} />);

    fireEvent.click(screen.getByTestId('chat-attach-button'));
    fireEvent.click(await screen.findByTestId('chat-attach-pdf'));

    const input = screen.getByTestId('chat-attach-input') as HTMLInputElement;
    await waitFor(() => {
      expect(input.accept).toContain('application/pdf');
    });

    const file = new File(['%PDF-hello'], 'brief.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(uploadChatAttachment).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId('chat-attachment-preview')).toHaveAttribute(
        'data-uploading',
        'false',
      );
    });
    expect(screen.getByText('brief.pdf')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('chat-attachment-remove'));
    await waitFor(() => {
      expect(deleteChatAttachment).toHaveBeenCalledWith('att-1');
    });
    expect(screen.queryByTestId('chat-attachment-preview')).not.toBeInTheDocument();
  });

  it('rejects oversized files client-side without uploading', async () => {
    withI18n(<ChatComposer onSubmit={vi.fn()} />);
    const input = screen.getByTestId('chat-attach-input') as HTMLInputElement;
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'big.pdf', {
      type: 'application/pdf',
    });
    fireEvent.change(input, { target: { files: [big] } });

    await waitFor(() => {
      expect(uploadChatAttachment).not.toHaveBeenCalled();
    });
    expect(screen.queryByTestId('chat-attachment-preview')).not.toBeInTheDocument();
  });

  it('submits attachment_id with the message', async () => {
    const onSubmit = vi.fn();
    uploadChatAttachment.mockResolvedValue({
      id: 'att-9',
      original_filename: 'note.txt',
      mime_type: 'text/plain',
      byte_size: 4,
      sha256: 'x',
      created_at: '2026-01-01T00:00:00Z',
      expires_at: '2026-01-01T12:00:00Z',
    });

    withI18n(<ChatComposer onSubmit={onSubmit} />);
    fireEvent.click(screen.getByTestId('chat-attach-button'));
    fireEvent.click(await screen.findByTestId('chat-attach-text'));
    const input = screen.getByTestId('chat-attach-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['hi'], 'note.txt', { type: 'text/plain' })] },
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat-attachment-preview')).toHaveAttribute(
        'data-uploading',
        'false',
      );
    });

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Summarize' } });
    fireEvent.submit(textarea.closest('form')!);

    expect(onSubmit).toHaveBeenCalledWith('Summarize', {
      attachmentId: 'att-9',
      attachmentMeta: {
        filename: 'note.txt',
        mimeType: 'text/plain',
        byteSize: 4,
      },
    });
  });
});
