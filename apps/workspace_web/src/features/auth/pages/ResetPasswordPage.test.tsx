import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ResetPasswordPage } from './ResetPasswordPage';

const completePasswordReset = vi.fn();

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', setTheme: vi.fn() }),
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/auth/AuthProvider', () => ({
  useAuth: () => ({
    status: 'unauthenticated',
    completePasswordReset,
  }),
}));

describe('ResetPasswordPage', () => {
  beforeEach(async () => {
    completePasswordReset.mockReset();
    completePasswordReset.mockResolvedValue({ workspaces: [{ id: 'w1' }] });
    await i18n.changeLanguage('en');
  });

  it('shows an error when the token is missing', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/reset-password']}>
            <Routes>
              <Route path="/reset-password" element={<ResetPasswordPage />} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    expect(screen.getByText(i18n.t('errors.invalidResetToken'))).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: i18n.t('auth.resetSubmit') }),
    ).toBeDisabled();
  });

  it('submits a new password and stores the session', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/reset-password?token=raw-token']}>
            <Routes>
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/" element={<div>home</div>} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    fireEvent.change(screen.getByLabelText(i18n.t('auth.password')), {
      target: { value: 'newpass456' },
    });
    fireEvent.change(screen.getByLabelText(i18n.t('auth.confirmPassword')), {
      target: { value: 'newpass456' },
    });
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.resetSubmit') }));

    await waitFor(() => {
      expect(completePasswordReset).toHaveBeenCalledWith('raw-token', 'newpass456');
      expect(screen.getByText('home')).toBeInTheDocument();
    });
  });
});
