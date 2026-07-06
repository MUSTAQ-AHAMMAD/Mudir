// ThemeContext.jsx — dark/light mode + locale (Arabic/English, RTL/LTR).
// Persists to localStorage and toggles the `dark` class + `dir` attribute on
// <html> so Tailwind's dark variant and RTL layout work app-wide.
import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';

const ThemeContext = createContext(null);

const THEME_KEY = 'mudir.theme';
const LOCALE_KEY = 'mudir.locale';

function initialTheme() {
  if (typeof window === 'undefined') return 'light';
  const stored = localStorage.getItem(THEME_KEY);
  if (stored) return stored;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function initialLocale() {
  if (typeof window === 'undefined') return 'ar';
  return localStorage.getItem(LOCALE_KEY) || 'ar';
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme);
  const [locale, setLocale] = useState(initialLocale);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('lang', locale);
    root.setAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr');
    localStorage.setItem(LOCALE_KEY, locale);
  }, [locale]);

  const toggleTheme = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), []);
  const toggleLocale = useCallback(() => setLocale((l) => (l === 'ar' ? 'en' : 'ar')), []);

  const value = useMemo(
    () => ({ theme, locale, setTheme, setLocale, toggleTheme, toggleLocale, isRTL: locale === 'ar' }),
    [theme, locale, toggleTheme, toggleLocale],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}

export default ThemeContext;
