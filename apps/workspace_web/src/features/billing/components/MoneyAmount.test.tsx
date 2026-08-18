import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MoneyAmount } from './MoneyAmount';

describe('MoneyAmount', () => {
  it('renders SAR with the official symbol and accessible name', () => {
    render(<MoneyAmount amount="99.00" currency="SAR" />);
    expect(screen.getByLabelText('SAR 99.00')).toBeInTheDocument();
    expect(screen.getByText('99.00')).toBeInTheDocument();
    expect(screen.queryByText(/SAR/)).not.toBeInTheDocument();
  });

  it('falls back to currency code for non-SAR', () => {
    render(<MoneyAmount amount="10.00" currency="USD" />);
    expect(screen.getByLabelText('USD 10.00')).toBeInTheDocument();
    expect(screen.getByText('USD 10.00')).toBeInTheDocument();
  });
});
