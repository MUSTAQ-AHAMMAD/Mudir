// StatCard.jsx — statistics card for the dashboard overview.
export default function StatCard({ label, value, icon, accent = 'green', hint }) {
  const accents = {
    green: 'text-brand-green',
    gold: 'text-brand-gold',
    red: 'text-red-600',
    amber: 'text-amber-600',
  };
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500 dark:text-gray-400">{label}</div>
        {icon && <span className="text-xl" aria-hidden="true">{icon}</span>}
      </div>
      <div className={`mt-2 text-3xl font-bold ${accents[accent] || accents.green}`}>
        {value ?? '—'}
      </div>
      {hint && <div className="mt-1 text-xs text-gray-400">{hint}</div>}
    </div>
  );
}
