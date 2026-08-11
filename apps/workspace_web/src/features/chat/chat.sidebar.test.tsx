import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import type { ReactNode } from 'react';
import i18n from '@/lib/i18n';
import { LayoutProvider } from '@/app/layouts/workspace/context';
import {
  ConversationListsShimmer,
  PinnedConversations,
  RecentConversations,
} from './components/ConversationLists';
import { QuickActions } from './components/QuickActions';
import type { Conversation } from '@/services/api/types';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

vi.mock('./hooks/useConversationMutations', () => ({
  useUpdateConversation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteConversation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useClearConversationHistory: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock('./hooks/useConversations', () => ({
  useConversations: () => ({
    data: [
      {
        id: 'c1',
        workspace_id: 'ws',
        expert_id: 'e1',
        user_id: 'u1',
        title: 'Fav chat',
        is_pinned: false,
        pinned_at: null,
        is_favorite: true,
        favorited_at: '2026-01-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        expert: null,
        last_message: null,
      },
    ] satisfies Conversation[],
    isLoading: false,
  }),
}));

function wrap(ui: ReactNode, route = '/chat') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[route]}>
          <LayoutProvider>{ui}</LayoutProvider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

const sample: Conversation = {
  id: 'c-recent',
  workspace_id: 'ws',
  expert_id: 'e1',
  user_id: 'u1',
  title: 'Policy Q',
  is_pinned: false,
  pinned_at: null,
  is_favorite: false,
  favorited_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  expert: null,
  last_message: null,
};

describe('ConversationLists Metronic actions', () => {
  it('renders recent row with an actions menu trigger', async () => {
    await i18n.changeLanguage('en');
    wrap(<RecentConversations conversations={[sample]} />);

    expect(screen.getByTestId('recent-conversations')).toBeInTheDocument();
    expect(screen.getByText('Policy Q')).toBeInTheDocument();
    expect(
      screen.getByTestId('conversation-actions-c-recent'),
    ).toHaveAttribute('aria-label', 'Conversation actions');
  });

  it('shows pinned placeholder when empty', async () => {
    await i18n.changeLanguage('en');
    wrap(<PinnedConversations conversations={[]} />);

    expect(screen.getByTestId('pinned-conversations')).toBeInTheDocument();
    expect(screen.getByText(/^Pinned$/i)).toBeInTheDocument();
    expect(screen.getByText(/No pinned chats/i)).toBeInTheDocument();
  });

  it('truncates long conversation titles and keeps the actions menu visible', async () => {
    await i18n.changeLanguage('ar');
    const longTitle =
      'ما الحد الأقصى لفترة التجربة وفق نظام العمل السعودي وما هي الاستثناءات المحتملة لهذه القاعدة';
    wrap(
      <RecentConversations
        conversations={[{ ...sample, id: 'c-long', title: longTitle }]}
      />,
    );

    const row = screen.getByTestId('conversation-row-c-long');
    expect(row.className).toMatch(/grid-cols-\[minmax\(0,1fr\)_auto\]/);
    const link = row.querySelector('a');
    expect(link).toHaveClass('truncate');
    expect(link).toHaveAttribute('title', longTitle);
    expect(link).toHaveTextContent(longTitle);
    expect(
      screen.getByTestId('conversation-actions-c-long'),
    ).toBeInTheDocument();
  });

  it('renders conversation list shimmer rows', async () => {
    await i18n.changeLanguage('en');
    wrap(<ConversationListsShimmer />);

    expect(screen.getByTestId('conversation-lists-shimmer')).toBeInTheDocument();
    expect(screen.getAllByTestId('conversation-row-shimmer').length).toBeGreaterThan(0);
    expect(screen.getByText(/^Pinned$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Recent$/i)).toBeInTheDocument();
  });
});

describe('QuickActions', () => {
  it('renders Favorites and Clear History', async () => {
    await i18n.changeLanguage('en');
    wrap(<QuickActions />);
    expect(screen.getByTestId('quick-actions')).toBeInTheDocument();
    expect(screen.getByText(/Quick Actions/i)).toBeInTheDocument();
    expect(screen.getByText(/^Favorites$/i)).toBeInTheDocument();
    expect(screen.getByText(/Clear History/i)).toBeInTheDocument();
    expect(screen.getByText(/Templates/i)).toBeInTheDocument();
  });
});
