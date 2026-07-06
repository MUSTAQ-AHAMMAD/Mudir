import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import StatusBadge from './StatusBadge';
import { renderWithProviders } from '../test/utils.jsx';

describe('StatusBadge', () => {
  it('renders a bilingual label for a status', () => {
    renderWithProviders(<StatusBadge status="ready" />);
    // default locale is Arabic
    expect(screen.getByText('جاهز')).toBeInTheDocument();
  });

  it('renders a custom label when provided', () => {
    renderWithProviders(<StatusBadge status="ready" label="Custom" />);
    expect(screen.getByText('Custom')).toBeInTheDocument();
  });
});
