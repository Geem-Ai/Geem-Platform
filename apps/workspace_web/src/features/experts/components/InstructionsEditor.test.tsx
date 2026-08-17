import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { InstructionsEditor } from './InstructionsEditor';

const generateExpertInstructions = vi.fn();

vi.mock('@/services/api/experts', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/experts')>(
    '@/services/api/experts',
  );
  return {
    ...actual,
    generateExpertInstructions: (...args: unknown[]) =>
      generateExpertInstructions(...args),
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('InstructionsEditor AI assist', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
    generateExpertInstructions.mockReset();
  });

  it('shows the generate button and opens the dialog', () => {
    const onChange = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <InstructionsEditor value="" onChange={onChange} expertName="Legal" />
      </I18nextProvider>,
    );

    fireEvent.click(screen.getByTestId('generate-instructions-button'));
    expect(screen.getByTestId('generate-instructions-dialog')).toBeInTheDocument();
    expect(screen.getByText('Legal')).toBeInTheDocument();
  });

  it('requires a brief before submit is enabled', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <InstructionsEditor value="" onChange={vi.fn()} />
      </I18nextProvider>,
    );
    fireEvent.click(screen.getByTestId('generate-instructions-button'));
    expect(screen.getByTestId('gen-instructions-submit')).toBeDisabled();
  });

  it('calls the API and applies generated instructions', async () => {
    generateExpertInstructions.mockResolvedValue({
      system_instructions: 'You are a precise employment counsel.',
    });
    const onChange = vi.fn();

    render(
      <I18nextProvider i18n={i18n}>
        <InstructionsEditor
          value="old text"
          onChange={onChange}
          expertName="Legal Assistant"
          expertDescription="Employment helper"
        />
      </I18nextProvider>,
    );

    fireEvent.click(screen.getByTestId('generate-instructions-button'));
    expect(
      screen.getByText(/This will replace the current system instructions/),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('gen-instructions-brief'), {
      target: { value: 'Help with contracts' },
    });
    fireEvent.click(screen.getByTestId('gen-instructions-submit'));

    await waitFor(() => {
      expect(generateExpertInstructions).toHaveBeenCalledWith({
        brief: 'Help with contracts',
        persona: null,
        audience: null,
        tone: null,
        constraints: null,
        name: 'Legal Assistant',
        description: 'Employment helper',
      });
    });

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('You are a precise employment counsel.');
    });
  });
});
