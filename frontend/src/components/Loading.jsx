// Loading.jsx — accessible loading spinner.
export default function Loading({ label = 'جارٍ التحميل… / Loading…', className = '' }) {
  return (
    <div className={`flex items-center justify-center gap-3 py-8 text-gray-500 ${className}`} role="status">
      <span
        className="h-6 w-6 animate-spin rounded-full border-2 border-brand-green border-t-transparent"
        aria-hidden="true"
      />
      <span className="text-sm">{label}</span>
      <span className="sr-only">{label}</span>
    </div>
  );
}
