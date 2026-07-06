// Modal.jsx — reusable, accessible modal dialog (Escape to close, backdrop click).
import { useEffect, useRef } from 'react';

export default function Modal({ open, onClose, title, children, footer, size = 'md' }) {
  const ref = useRef(null);
  const sizes = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' };

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    document.addEventListener('keydown', onKey);
    ref.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4 print:hidden"
      onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`card w-full ${sizes[size] || sizes.md} bg-white p-5 outline-none dark:bg-brand-greenDark`}
      >
        {title && (
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-brand-green dark:text-brand-gold">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              className="text-2xl leading-none text-gray-400 hover:text-gray-600"
              aria-label="Close dialog"
            >
              ×
            </button>
          </div>
        )}
        <div>{children}</div>
        {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}
