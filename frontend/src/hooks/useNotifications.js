// useNotifications.js — thin wrapper over AppContext's toast queue so pages can
// fire notifications without importing the context directly.
import { useApp } from '../context/AppContext';

export function useNotifications() {
  const { toasts, addToast, removeToast } = useApp();
  return {
    toasts,
    notify: addToast,
    success: (message, opts) => addToast({ message, type: 'success', ...opts }),
    error: (message, opts) => addToast({ message, type: 'error', ...opts }),
    info: (message, opts) => addToast({ message, type: 'info', ...opts }),
    warning: (message, opts) => addToast({ message, type: 'warning', ...opts }),
    dismiss: removeToast,
  };
}

export default useNotifications;
