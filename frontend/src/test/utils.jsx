// Test helpers: render a component wrapped in the app providers.
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '../context/ThemeContext';
import { AppProvider } from '../context/AppContext';

export function renderWithProviders(ui, { route = '/' } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AppProvider>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </AppProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}
