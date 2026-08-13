import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ExpertApiIdField } from './ExpertApiIdField';

vi.mock('@/lib/clipboard', () => ({
  copyText: vi.fn(async () => true),
}));

describe('ExpertApiIdField', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('copies the public expert UUID', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <ExpertApiIdField expertId="11111111-2222-3333-4444-555555555555" />
      </I18nextProvider>,
    );
    expect(screen.getByTestId('expert-api-id')).toHaveTextContent(
      '11111111-2222-3333-4444-555555555555',
    );
    expect(screen.getByText(/X-Geem-Expert-Id/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('copy-expert-api-id'));
    const { copyText } = await import('@/lib/clipboard');
    await waitFor(() => {
      expect(copyText).toHaveBeenCalledWith('11111111-2222-3333-4444-555555555555');
    });
  });
});
