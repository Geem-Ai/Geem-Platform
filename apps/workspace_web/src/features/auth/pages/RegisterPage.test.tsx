import { act, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { RegisterPage } from './RegisterPage';

const register = vi.fn();
const authState: { status: 'unauthenticated' | 'authenticated' } = {
  status: 'unauthenticated',
};

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', setTheme: vi.fn() }),
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/auth/AuthProvider', () => ({
  useAuth: () => ({
    status: authState.status,
    register,
  }),
}));

describe('RegisterPage', () => {
  beforeEach(async () => {
    register.mockReset();
    authState.status = 'unauthenticated';
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('returns authenticated users to the invitation accept route', async () => {
    authState.status = 'authenticated';
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter
            initialEntries={[
              {
                pathname: '/register',
                state: { from: '/invitations/accept?token=invite-token' },
              },
            ]}
          >
            <Routes>
              <Route path="/register" element={<RegisterPage />} />
              <Route
                path="/invitations/accept"
                element={<div data-testid="invitation-return" />}
              />
              <Route path="/" element={<div data-testid="home" />} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    expect(screen.getByTestId('invitation-return')).toBeInTheDocument();
    expect(screen.queryByTestId('home')).not.toBeInTheDocument();
  });
});
