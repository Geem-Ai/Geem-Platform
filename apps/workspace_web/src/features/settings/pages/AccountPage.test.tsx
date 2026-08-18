import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { AccountPage } from './AccountPage';

const changePassword = vi.fn();
const toastSuccess = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: vi.fn(),
  },
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { email: 'user@example.com' },
  }),
}));

vi.mock('@/services/api', () => ({
  changePassword: (...args: unknown[]) => changePassword(...args),
}));

describe('AccountPage', () => {
  beforeEach(async () => {
    changePassword.mockReset();
    toastSuccess.mockReset();
    changePassword.mockResolvedValue({ ok: true });
    await i18n.changeLanguage('en');
  });

  it('submits change password and shows success', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <AccountPage />
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    expect(screen.getByTestId('account-email')).toHaveTextContent('user@example.com');

    fireEvent.change(screen.getByLabelText(i18n.t('account.currentPassword')), {
      target: { value: 'oldpass123' },
    });
    fireEvent.change(screen.getByLabelText(i18n.t('account.newPassword')), {
      target: { value: 'newpass456' },
    });
    fireEvent.change(screen.getByLabelText(i18n.t('auth.confirmPassword')), {
      target: { value: 'newpass456' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('account.changePasswordSubmit') }),
    );

    await waitFor(() => {
      expect(changePassword).toHaveBeenCalledWith('oldpass123', 'newpass456');
      expect(toastSuccess).toHaveBeenCalled();
    });
  });

  it('shows mismatch error without calling the API', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <AccountPage />
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    fireEvent.change(screen.getByLabelText(i18n.t('account.currentPassword')), {
      target: { value: 'oldpass123' },
    });
    fireEvent.change(screen.getByLabelText(i18n.t('account.newPassword')), {
      target: { value: 'newpass456' },
    });
    fireEvent.change(screen.getByLabelText(i18n.t('auth.confirmPassword')), {
      target: { value: 'different' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('account.changePasswordSubmit') }),
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('errors.passwordMismatch'))).toBeInTheDocument();
    });
    expect(changePassword).not.toHaveBeenCalled();
  });
});
