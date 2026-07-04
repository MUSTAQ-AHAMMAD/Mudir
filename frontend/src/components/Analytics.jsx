// Analytics.jsx — headline metrics + simple bar charts. Includes a lightweight
// "Export as PDF" action that uses the browser's print-to-PDF (no extra deps).
import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';

function Metric({ label, value }) {
  return (
    <div className="rounded-xl border bg-white p-4">
      <div className="text-3xl font-bold text-brand-green">{value ?? '—'}</div>
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );
}

/** Minimal horizontal bar chart rendered from a { key: count } map. */
function BarChart({ data, color }) {
  const entries = Object.entries(data || {});
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (entries.length === 0) return <p className="text-sm text-gray-400">No data.</p>;
  return (
    <div className="space-y-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="w-28 text-sm capitalize truncate">{key}</span>
          <div className="flex-1 bg-gray-100 rounded h-4">
            <div className={`h-4 rounded ${color}`} style={{ width: `${(value / max) * 100}%` }} />
          </div>
          <span className="w-8 text-sm text-right">{value}</span>
        </div>
      ))}
    </div>
  );
}

export default function Analytics() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const printRef = useRef(null);

  useEffect(() => {
    api.analytics().then(setData).catch((e) => setError(e.message));
  }, []);

  // Print-to-PDF: the browser's native dialog lets the user "Save as PDF".
  const exportPdf = () => window.print();

  if (error) return <p className="text-red-600">Error: {error}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;

  return (
    <div ref={printRef}>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-brand-green">التحليلات / Analytics</h1>
        <button className="px-3 py-2 rounded-lg border print:hidden" onClick={exportPdf}>
          ⬇️ Export as PDF
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-4 mb-6">
        <Metric label="Total projects" value={data.totals.projects} />
        <Metric label="Completed" value={data.totals.completed} />
        <Metric label="Avg completion (days)" value={data.avgCompletionDays} />
        <Metric label="Escalations" value={data.totals.escalations} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="rounded-xl border bg-white p-4">
          <h3 className="font-semibold mb-3">Delays by team</h3>
          <BarChart data={data.delaysByTeam} color="bg-red-400" />
        </div>
        <div className="rounded-xl border bg-white p-4">
          <h3 className="font-semibold mb-3">Escalations by project</h3>
          <BarChart data={data.escalationsByProject} color="bg-brand-gold" />
        </div>
      </div>
    </div>
  );
}
