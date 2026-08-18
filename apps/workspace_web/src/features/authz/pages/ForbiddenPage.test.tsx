import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import i18n from '@/lib/i18n';
import { ForbiddenPage } from './ForbiddenPage';

describe('ForbiddenPage', () => {
  it('renders a localized 403 without sending the user to /overview', async () => {
    await i18n.changeLanguage('en');
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <ForbiddenPage />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.getByTestId('forbidden-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: i18n.t('errors.forbiddenTitle') })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: i18n.t('errors.goHome') })).toHaveAttribute(
      'href',
      '/',
    );
  });

  it('renders Arabic copy in RTL', async () => {
    await i18n.changeLanguage('ar');
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <ForbiddenPage />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.getByTestId('forbidden-page')).toHaveTextContent('الوصول مرفوض');
    expect(document.documentElement.dir).toBe('rtl');
  });
});
