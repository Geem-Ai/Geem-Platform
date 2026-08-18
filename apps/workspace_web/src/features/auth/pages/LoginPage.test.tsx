import { act, fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { LoginPage } from './LoginPage';

const login = vi.fn();
const clearSessionExpired = vi.fn();
const authState: {
  status: 'unauthenticated' | 'authenticated' | 'loading';
  sessionExpired: boolean;
} = {
  status: 'unauthenticated',
  sessionExpired: false,
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
    login,
    sessionExpired: authState.sessionExpired,
    clearSessionExpired,
  }),
}));

async function renderLogin() {
  await act(async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </I18nextProvider>,
    );
  });
}

describe('LoginPage', () => {
  beforeEach(async () => {
    login.mockReset();
    clearSessionExpired.mockReset();
    authState.status = 'unauthenticated';
    authState.sessionExpired = false;
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('renders branded layout, form fields, and locale chrome', async () => {
    await renderLogin();

    expect(screen.getByTestId('auth-layout')).toBeInTheDocument();
    expect(screen.getByTestId('auth-brand-panel')).toBeInTheDocument();
    expect(screen.getByTestId('login-form')).toBeInTheDocument();
    expect(screen.getByLabelText(i18n.t('auth.email'))).toBeInTheDocument();
    expect(screen.getByLabelText(i18n.t('auth.password'))).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: i18n.t('auth.signIn') }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('forgot-password-link')).toHaveAttribute(
      'href',
      '/forgot-password',
    );
    expect(screen.getByTestId('auth-language-ar')).toBeInTheDocument();
    expect(screen.getByTestId('auth-theme-toggle')).toBeInTheDocument();
  });

  it('toggles password visibility', async () => {
    await renderLogin();

    const password = screen.getByLabelText(i18n.t('auth.password'));
    const toggle = screen.getByTestId('auth-password-toggle-password');
    expect(password).toHaveAttribute('type', 'password');

    fireEvent.click(toggle);
    expect(password).toHaveAttribute('type', 'text');
    expect(toggle).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(toggle);
    expect(password).toHaveAttribute('type', 'password');
  });

  it('shows a session-expired warning', async () => {
    authState.sessionExpired = true;
    await renderLogin();

    expect(screen.getByTestId('auth-alert')).toHaveAttribute('data-tone', 'warning');
    expect(screen.getByText(i18n.t('errors.sessionExpired'))).toBeInTheDocument();
  });

  it('returns authenticated users to the payment result instead of home', async () => {
    authState.status = 'authenticated';
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter
            initialEntries={[
              {
                pathname: '/login',
                state: { from: '/billing/payment/success?purchase=pur-1' },
              },
            ]}
          >
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/billing/payment/success"
                element={<div data-testid="payment-success" />}
              />
              <Route path="/" element={<div data-testid="home" />} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    expect(screen.getByTestId('payment-success')).toBeInTheDocument();
    expect(screen.queryByTestId('home')).not.toBeInTheDocument();
  });

  it('returns authenticated users to the invitation accept route', async () => {
    authState.status = 'authenticated';
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter
            initialEntries={[
              {
                pathname: '/login',
                state: { from: '/invitations/accept?token=invite-token' },
              },
            ]}
          >
            <Routes>
              <Route path="/login" element={<LoginPage />} />
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
