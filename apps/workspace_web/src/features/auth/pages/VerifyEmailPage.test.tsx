import { act, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { VerifyEmailPage } from './VerifyEmailPage';
import { ApiError } from '@/services/api/errors';

const completeEmailVerification = vi.fn();

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', setTheme: vi.fn() }),
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/auth/AuthProvider', () => ({
  useAuth: () => ({
    status: 'unauthenticated',
    completeEmailVerification,
  }),
}));

describe('VerifyEmailPage', () => {
  beforeEach(async () => {
    completeEmailVerification.mockReset();
    completeEmailVerification.mockResolvedValue({ workspaces: [{ id: 'w1' }] });
    await i18n.changeLanguage('en');
  });

  it('shows an error when the token is missing', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/verify-email']}>
            <Routes>
              <Route path="/verify-email" element={<VerifyEmailPage />} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    expect(screen.getByText(i18n.t('errors.invalidVerificationToken'))).toBeInTheDocument();
    expect(completeEmailVerification).not.toHaveBeenCalled();
  });

  it('verifies the token and continues home', async () => {
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/verify-email?token=raw-token']}>
            <Routes>
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route path="/" element={<div>home</div>} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    await waitFor(() => {
      expect(completeEmailVerification).toHaveBeenCalledWith('raw-token');
      expect(screen.getByText('home')).toBeInTheDocument();
    });
  });

  it('shows API errors from a bad token', async () => {
    completeEmailVerification.mockRejectedValue(
      new ApiError('bad', {
        status: 400,
        code: 'invalid_verification_token',
      }),
    );
    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/verify-email?token=bad']}>
            <Routes>
              <Route path="/verify-email" element={<VerifyEmailPage />} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>,
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText(i18n.t('errors.invalidVerificationToken')),
      ).toBeInTheDocument();
    });
  });
});
