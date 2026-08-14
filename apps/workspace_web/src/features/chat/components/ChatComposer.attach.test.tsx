import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/lib/i18n';
import { ChatComposer } from './ChatComposer';

function withI18n(ui: React.ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe('ChatComposer attachments', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows fake upload progress and can remove the attachment', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
    withI18n(<ChatComposer onSubmit={vi.fn()} />);

    const input = screen.getByTestId('chat-attach-input') as HTMLInputElement;
    const file = new File(['hello'], 'brief.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByTestId('chat-attachment-preview')).toHaveAttribute(
      'data-uploading',
      'true',
    );
    expect(screen.getByText('brief.pdf')).toBeInTheDocument();
    expect(screen.getByText('PDF')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(screen.getByTestId('chat-attachment-preview')).toHaveAttribute(
      'data-uploading',
      'false',
    );

    fireEvent.click(screen.getByTestId('chat-attachment-remove'));
    expect(screen.queryByTestId('chat-attachment-preview')).not.toBeInTheDocument();
  });
});
