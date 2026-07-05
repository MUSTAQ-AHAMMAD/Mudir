// Header.jsx — top bar with the company selector, theme/locale toggles and the
// authenticated user menu.
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../hooks/useAuth';

export default function Header({ onMenu }) {
  const { companies, companyId, setCompanyId } = useApp();
  const { theme, toggleTheme, locale, toggleLocale } = useTheme();
  const { user, signOut } = useAuth();

  return (
    <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-gray-200 bg-white/90 px-4 py-3 backdrop-blur dark:border-white/10 dark:bg-brand-greenDark/90 print:hidden">
      <button
        type="button"
        className="btn-outline px-2 py-1 md:hidden"
        onClick={onMenu}
        aria-label="Toggle navigation menu"
      >
        ☰
      </button>

      <label className="flex items-center gap-2">
        <span className="sr-only">Company</span>
        <select
          className="input"
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value)}
          aria-label="Select company"
        >
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <div className="ms-auto flex items-center gap-2">
        <button
          type="button"
          className="btn-outline px-2 py-1"
          onClick={toggleLocale}
          aria-label="Switch language"
        >
          {locale === 'ar' ? 'EN' : 'ع'}
        </button>
        <button
          type="button"
          className="btn-outline px-2 py-1"
          onClick={toggleTheme}
          aria-label="Toggle dark mode"
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
        {user && (
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-gray-600 dark:text-gray-300 sm:inline">
              {user.user_metadata?.name || user.email}
            </span>
            <button type="button" className="btn-outline px-2 py-1" onClick={signOut}>
              خروج / Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
