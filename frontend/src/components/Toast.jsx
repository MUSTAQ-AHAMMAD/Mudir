// Toast.jsx — notification toasts rendered from the AppContext queue.
import { useApp } from '../context/AppContext';

const STYLES = {
  success: 'bg-brand-green text-white',
  error: 'bg-red-600 text-white',
  warning: 'bg-brand-gold text-brand-greenDark',
  info: 'bg-gray-800 text-white dark:bg-white/10',
};

const ICONS = { success: '✅', error: '⛔', warning: '⚠️', info: 'ℹ️' };

export default function Toast() {
  const { toasts, removeToast } = useApp();
  if (toasts.length === 0) return null;
  return (
    <div
      className="fixed top-4 left-1/2 z-50 flex -translate-x-1/2 flex-col gap-2 print:hidden"
      role="region"
      aria-label="Notifications"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="alert"
          className={`flex animate-toast-in items-center gap-3 rounded-lg px-4 py-2 shadow-lg ${STYLES[t.type] || STYLES.info}`}
        >
          <span aria-hidden="true">{ICONS[t.type] || ICONS.info}</span>
          <span className="text-sm">{t.message}</span>
          <button
            type="button"
            className="ml-2 text-lg leading-none opacity-70 hover:opacity-100"
            onClick={() => removeToast(t.id)}
            aria-label="Dismiss notification"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
