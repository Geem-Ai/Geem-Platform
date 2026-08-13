import { render } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it } from 'vitest';
import i18n from '@/lib/i18n';
import { DocumentTitle } from './DocumentTitle';

function renderTitle(title?: string) {
  return render(
    <HelmetProvider>
      <I18nextProvider i18n={i18n}>
        <DocumentTitle title={title} />
      </I18nextProvider>
    </HelmetProvider>,
  );
}

describe('DocumentTitle', () => {
  it('sets the product default when no page title is given', async () => {
    await i18n.changeLanguage('en');
    const view = renderTitle();
    expect(document.title).toBe('Geem | Arabic-first AI workspace');
    view.unmount();
  });

  it('prefixes the page label with the product name', async () => {
    await i18n.changeLanguage('en');
    const view = renderTitle('Chat');
    expect(document.title).toBe('Chat | Geem');
    view.unmount();
  });
});
