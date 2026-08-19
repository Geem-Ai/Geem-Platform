import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { CheckEmailPage } from './CheckEmailPage';

const resendVerification = vi.fn();

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', setTheme: vi.fn() }),
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/auth/AuthProvider', () => ({
  useAuth: () => ({
    status: 'unauthenticated',
  }),
}));

vi.mock('@/services/api', () => ({
  resendVerification: (...args: unknown[]) => resendVerification(...args),
}));

describe('CheckEmailPage', () => {
  beforeEach(async () => {
    resendVerification.mockReset();
    resendVerification.mockResolvedValue({ ok: true });
    await i18n.changeLanguage('en');
  });

  it('shows the known email and resends', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter
            initialEntries={[
              { pathname: '/check-email', state: { email: 'new@example.com' } },
            ]}
          >
            <CheckEmailPage />
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    expect(screen.getByTestId('check-email-form')).toBeInTheDocument();
    expect(
      screen.getByText(i18n.t('auth.checkEmailSubtitleKnown', { email: 'new@example.com' })),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('auth.checkEmailResend') }),
    );

    await waitFor(() => {
      expect(resendVerification).toHaveBeenCalledWith('new@example.com');
      expect(screen.getByText(i18n.t('auth.checkEmailResent'))).toBeInTheDocument();
    });
  });
});
