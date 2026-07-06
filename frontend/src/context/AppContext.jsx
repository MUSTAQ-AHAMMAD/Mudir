// AppContext.jsx — global UI state: the selected company and the toast queue.
// Data fetching lives in React Query hooks; this holds only cross-cutting UI
// state that many components need.
import { createContext, useContext, useMemo, useState, useCallback, useRef } from 'react';

const AppContext = createContext(null);

// A small default company list; real deployments load these from the backend.
const DEFAULT_COMPANIES = [
  { id: 'default', name: 'Mudir Retail' },
];

export function AppProvider({ children }) {
  const [companies, setCompanies] = useState(DEFAULT_COMPANIES);
  const [companyId, setCompanyId] = useState(DEFAULT_COMPANIES[0].id);
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    ({ message, type = 'info', timeout = 4000 }) => {
      idRef.current += 1;
      const id = idRef.current;
      setToasts((prev) => [...prev, { id, message, type }]);
      if (timeout) setTimeout(() => removeToast(id), timeout);
      return id;
    },
    [removeToast],
  );

  const value = useMemo(
    () => ({
      companies,
      setCompanies,
      companyId,
      setCompanyId,
      company: companies.find((c) => c.id === companyId) || null,
      toasts,
      addToast,
      removeToast,
    }),
    [companies, companyId, toasts, addToast, removeToast],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}

export default AppContext;
