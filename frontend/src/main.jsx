// main.jsx — React entrypoint. Wraps the app in all global providers:
// Router, React Query, App/Auth/Theme contexts.
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import { AppProvider } from './context/AppContext';
import './styles/index.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } },
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <AppProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AppProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
