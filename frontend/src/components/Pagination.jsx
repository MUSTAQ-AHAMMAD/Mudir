// Pagination.jsx — simple page navigator.
export default function Pagination({ page, pageCount, onPage }) {
  if (pageCount <= 1) return null;
  const go = (p) => onPage?.(Math.max(1, Math.min(pageCount, p)));
  return (
    <nav className="mt-4 flex items-center justify-center gap-1" aria-label="Pagination">
      <button className="btn-outline px-3 py-1" onClick={() => go(page - 1)} disabled={page <= 1}>
        ‹
      </button>
      {Array.from({ length: pageCount }, (_, i) => i + 1)
        .filter((p) => Math.abs(p - page) <= 2 || p === 1 || p === pageCount)
        .map((p, idx, arr) => (
          <span key={p} className="flex items-center">
            {idx > 0 && p - arr[idx - 1] > 1 && <span className="px-1 text-gray-400">…</span>}
            <button
              className={`rounded-lg px-3 py-1 text-sm ${
                p === page ? 'bg-brand-green text-white' : 'hover:bg-gray-100 dark:hover:bg-white/10'
              }`}
              onClick={() => go(p)}
              aria-current={p === page ? 'page' : undefined}
            >
              {p}
            </button>
          </span>
        ))}
      <button className="btn-outline px-3 py-1" onClick={() => go(page + 1)} disabled={page >= pageCount}>
        ›
      </button>
    </nav>
  );
}
