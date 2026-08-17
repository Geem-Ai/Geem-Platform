import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/lib/i18n';
import { ChatMessage } from './components/ChatMessage';
import { ChatStarter } from './components/ChatStarter';
import { CitationList } from './components/CitationList';
import type { Expert } from '@/services/api/types';

function withI18n(ui: React.ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

function mockReducedMotion(reduced: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: reduced && query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

beforeEach(() => {
  mockReducedMotion(false);
});


const readyExpert: Expert = {
  id: 'exp-1',
  type: 'workspace',
  ownership: 'workspace',
  workspace_id: 'ws-1',
  name: 'Legal',
  description: 'Law docs',
  icon_url: null,
  system_instructions: null,
  rag_config: null,
  status: 'ready',
  visibility: 'workspace',
  availability_mode: 'workspace',
  created_by: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  knowledge_document_count: 2,
};

const platformExpert: Expert = {
  ...readyExpert,
  id: 'exp-p',
  name: 'Geem Legal',
  ownership: 'platform',
  type: 'platform',
  workspace_id: null,
  knowledge_document_count: 0,
};

const geemGeneral: Expert = {
  ...platformExpert,
  id: 'exp-geem',
  name: 'Geem',
  knowledge_mode: 'general',
  description: 'General assistant',
};

describe('ChatStarter Experts picker', () => {
  it('requires an Expert before submit is enabled', () => {
    const onSubmit = vi.fn();
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId={null}
        onSelectExpert={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByText(/Select an Expert before sending/i)).toBeInTheDocument();
    expect(screen.getByTestId('experts-picker-button')).toHaveTextContent(/Experts/i);
    const send = screen.getByRole('button', { name: /send/i });
    expect(send).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Select an Expert to start/i), {
      target: { value: 'Hello' },
    });
    expect(send).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('opens modal with Workspace and Geem sections and search', () => {
    const onSelect = vi.fn();
    withI18n(
      <ChatStarter
        experts={[readyExpert, platformExpert, geemGeneral]}
        selectedExpertId={null}
        onSelectExpert={onSelect}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('experts-picker-button'));
    const dialog = screen.getByTestId('expert-picker-dialog');
    expect(within(dialog).getByText(/My Experts/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/Geem Experts/i)).toBeInTheDocument();

    const geemGeneralRow = within(dialog).getByTestId('expert-option-exp-geem');
    expect(geemGeneralRow).toHaveAttribute('data-knowledge-mode', 'general');
    expect(within(dialog).getByText(/^General$/i)).toBeInTheDocument();

    // Geem General is listed before other platform Experts in the Geem section.
    const platformIds = within(dialog)
      .getAllByTestId(/expert-option-exp-/)
      .map((el) => el.getAttribute('data-testid'))
      .filter((id) => id === 'expert-option-exp-geem' || id === 'expert-option-exp-p');
    expect(platformIds[0]).toBe('expert-option-exp-geem');

    fireEvent.change(screen.getByTestId('expert-picker-search'), {
      target: { value: 'Geem Legal' },
    });
    expect(within(dialog).getByTestId('expert-option-exp-p')).toBeInTheDocument();
    expect(within(dialog).queryByTestId('expert-option-exp-1')).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByTestId('expert-option-exp-p'));
    expect(onSelect).toHaveBeenCalledWith('exp-p');
  });

  it('preselects Expert from deep-link on the Experts button', () => {
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId="exp-1"
        onSelectExpert={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByTestId('experts-picker-button')).toHaveTextContent('Legal');
  });

  it('enables send after Expert is selected and content entered', () => {
    const onSubmit = vi.fn();
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId="exp-1"
        onSelectExpert={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    const input = screen.getByLabelText(/Ask Legal a question/i);
    fireEvent.change(input, { target: { value: 'What is the policy?' } });
    const send = screen.getByRole('button', { name: /send/i });
    expect(send).not.toBeDisabled();
    fireEvent.click(send);
    expect(onSubmit).toHaveBeenCalledWith('What is the policy?');
  });
});

describe('ChatMessage citations + retry', () => {
  it('renders citations from structured metadata', () => {
    withI18n(
      <ChatMessage
        message={{
          id: 'a1',
          role: 'assistant',
          content: 'Answer',
          citations: [
            {
              chunk_id: 'c1',
              document_id: 'd1',
              document_title: 'Policy.pdf',
              page: 3,
              snippet: 'Relevant clause',
            },
          ],
          status: 'completed',
          created_at: '2026-01-01T00:00:00Z',
        }}
      />,
    );
    expect(screen.getByText('Policy.pdf')).toBeInTheDocument();
    expect(screen.getByText(/Relevant clause/)).toBeInTheDocument();
  });

  it('shows retry on failed assistant without requiring a new user bubble', () => {
    const onRetry = vi.fn();
    withI18n(
      <ChatMessage
        message={{
          id: 'a-fail',
          role: 'assistant',
          content: '',
          citations: [],
          status: 'failed',
          created_at: '2026-01-01T00:00:00Z',
          errorMessage: 'Unable to complete the response.',
        }}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByText(/Unable to complete the response/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledWith('a-fail');
  });

  it('uses Geem brand avatar for the assistant face', () => {
    withI18n(
      <ChatMessage
        message={{
          id: 'a1',
          role: 'assistant',
          content: 'Hi',
          citations: [],
          status: 'completed',
          created_at: '2026-01-01T00:00:00Z',
        }}
      />,
    );
    const img = screen.getByTestId('geem-assistant-avatar');
    expect(img.getAttribute('data')).toContain('/brand/geem-animated.svg');
    expect(img.getAttribute('aria-label')).toBe('Geem');
    expect(img.getAttribute('data-geem-mascot')).toBe('animated');
    expect(screen.getByTestId('message-timestamp')).toBeInTheDocument();
  });

  it('shows typewriter thinking status while streaming with no content', () => {
    withI18n(
      <ChatMessage
        message={{
          id: 'a-stream',
          role: 'assistant',
          content: '',
          citations: [],
          status: 'streaming',
          created_at: '2026-01-01T00:00:00Z',
        }}
        isStreaming
      />,
    );
    expect(screen.getByTestId('thinking-status')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/Geem is thinking/i);
  });
});

describe('CitationList', () => {
  it('renders after reload-shaped citation payloads', () => {
    withI18n(
      <CitationList
        citations={[
          {
            chunk_id: 'x',
            document_id: 'y',
            document_title: 'Handbook',
            page: 2,
            snippet: 'text',
          },
        ]}
      />,
    );
    expect(screen.getByText('Handbook')).toBeInTheDocument();
    expect(screen.getByText(/p\.\s*2/i)).toBeInTheDocument();
  });

  it('hides markdown image placeholders in snippets', () => {
    withI18n(
      <CitationList
        citations={[
          {
            chunk_id: 'c2',
            document_id: 'd2',
            document_title: 'كتيب نظام السعد.pdf',
            page: 2,
            snippet:
              'تطبيق خاص مبيعات ![img-0.jpeg](img-0.jpeg) إدارة مطبخ ![img-1.jpeg](img-1.jpeg) فواتير إلكترونية',
          },
        ]}
      />,
    );
    expect(screen.getByText('كتيب نظام السعد.pdf')).toBeInTheDocument();
    const snippet = screen.getByTestId('citation-snippet');
    expect(snippet).toHaveTextContent('تطبيق خاص مبيعات إدارة مطبخ فواتير إلكترونية');
    expect(snippet.textContent).not.toContain('![img-0.jpeg]');
    expect(snippet.textContent).not.toContain('img-0.jpeg');
  });

  it('offers show more for long sanitized snippets', () => {
    const longSnippet = `${'ميزة مهمة في النظام '.repeat(20)}نهاية`;
    withI18n(
      <CitationList
        citations={[
          {
            chunk_id: 'c3',
            document_id: 'd3',
            document_title: 'Doc.pdf',
            page: 1,
            snippet: longSnippet,
          },
        ]}
      />,
    );
    const toggle = screen.getByRole('button', { name: /show more/i });
    fireEvent.click(toggle);
    expect(screen.getByRole('button', { name: /show less/i })).toBeInTheDocument();
  });
});

describe('Arabic RTL chat smoke', () => {
  it('renders starter strings in Arabic', async () => {
    await i18n.changeLanguage('ar');
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId={null}
        onSelectExpert={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText(/كيف يمكن لـ Geem مساعدتك اليوم؟/)).toBeInTheDocument();
    expect(screen.getByTestId('experts-picker-button')).toHaveTextContent('الخبراء');
    expect(i18n.language).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
    await i18n.changeLanguage('en');
  });
});

describe('Sample prompt suggestions', () => {
  it('renders sample prompts on the starter', async () => {
    await i18n.changeLanguage('en');
    mockReducedMotion(true);
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId="exp-1"
        onSelectExpert={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    const list = screen.getByTestId('sample-prompts');
    expect(list).toBeInTheDocument();
    const chips = within(list).getAllByTestId(/sample-prompt-/);
    expect(chips).toHaveLength(5);
    expect(chips.every((c) => c.getAttribute('data-done') === 'true')).toBe(true);
  });

  it('submits when a finished chip is clicked with an Expert selected', async () => {
    await i18n.changeLanguage('en');
    mockReducedMotion(true);
    const onSubmit = vi.fn();
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId="exp-1"
        onSelectExpert={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const chip = screen.getByTestId('sample-prompt-0');
    const promptText = chip.textContent?.trim() ?? '';
    expect(promptText.length).toBeGreaterThan(0);
    fireEvent.click(chip);

    expect(onSubmit).toHaveBeenCalledWith(promptText);
    const input = screen.getByLabelText(/Ask Legal a question/i);
    expect(input).toHaveValue(promptText);
  });

  it('only fills the composer when no Expert is selected', async () => {
    await i18n.changeLanguage('en');
    mockReducedMotion(true);
    const onSubmit = vi.fn();
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId={null}
        onSelectExpert={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const chip = screen.getByTestId('sample-prompt-0');
    const promptText = chip.textContent?.trim() ?? '';
    fireEvent.click(chip);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/Select an Expert to start/i)).toHaveValue(
      promptText,
    );
  });

  it('does not pause typewriter from autofocus (P1)', async () => {
    await i18n.changeLanguage('en');
    mockReducedMotion(false);
    vi.useFakeTimers();
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId="exp-1"
        onSelectExpert={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    // Autofocus runs on mount; typewriter should still advance.
    for (let i = 0; i < 20; i += 1) {
      await vi.advanceTimersByTimeAsync(30);
    }
    const list = screen.getByTestId('sample-prompts');
    const chips = within(list).queryAllByTestId(/sample-prompt-/);
    expect(chips.length).toBeGreaterThan(0);
    expect((chips[0]?.textContent ?? '').replace(/\s/g, '').length).toBeGreaterThan(1);
    vi.useRealTimers();
  });

  it('user focus pauses and hides incomplete chips (P2)', async () => {
    await i18n.changeLanguage('en');
    mockReducedMotion(false);
    vi.useFakeTimers();
    withI18n(
      <ChatStarter
        experts={[readyExpert]}
        selectedExpertId="exp-1"
        onSelectExpert={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    await vi.advanceTimersByTimeAsync(30 * 3);
    const input = screen.getByLabelText(/Ask Legal a question/i);
    fireEvent.focus(input);

    // Incomplete chip dropped; may be zero finished chips yet.
    const chips = within(screen.getByTestId('sample-prompts')).queryAllByTestId(
      /sample-prompt-/,
    );
    expect(chips.every((c) => c.getAttribute('data-done') === 'true')).toBe(true);
    vi.useRealTimers();
  });
});
