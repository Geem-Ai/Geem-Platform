import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ForgotPasswordPage } from './ForgotPasswordPage';

const forgotPassword = vi.fn();

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
  forgotPassword: (...args: unknown[]) => forgotPassword(...args),
}));

describe('ForgotPasswordPage', () => {
  beforeEach(async () => {
    forgotPassword.mockReset();
    forgotPassword.mockResolvedValue({ ok: true });
    await i18n.changeLanguage('en');
  });

  it('shows success state after submit', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <ForgotPasswordPage />
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    fireEvent.change(screen.getByLabelText(i18n.t('auth.email')), {
      target: { value: 'user@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.forgotSubmit') }));

    await waitFor(() => {
      expect(forgotPassword).toHaveBeenCalledWith('user@example.com');
      expect(screen.getByTestId('forgot-password-success')).toBeInTheDocument();
    });
  });
});
