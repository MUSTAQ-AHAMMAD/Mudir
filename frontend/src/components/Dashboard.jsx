// Dashboard.jsx — project list with status badges, search and filtering.
// Overdue projects (opening date in the past and not completed) are highlighted.
import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';
import StatusBadge from './StatusBadge';

const STATUS_OPTIONS = ['', 'property_pending', 'marketing_pending', 'it_pending', 'ready', 'completed'];

/** Is a project past its opening date without being completed? */
function isOverdue(project) {
  if (!project.opening_date || project.status === 'completed') return false;
  return new Date(project.opening_date) < new Date();
}

export default function Dashboard() {
  const [projects, setProjects] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .listProjects(statusFilter || undefined)
      .then((data) => setProjects(data.projects || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  const filtered = useMemo(
    () =>
      projects.filter(
        (p) =>
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          p.code.toLowerCase().includes(search.toLowerCase()),
      ),
    [projects, search],
  );

  return (
    <div>
      <h1 className="text-2xl font-bold text-brand-green mb-1">المشاريع / Projects</h1>
      <p className="text-sm text-gray-500 mb-4">Track every store opening across all teams.</p>

      <div className="flex flex-wrap gap-3 mb-4">
        <input
          className="border rounded-lg px-3 py-2 w-64"
          placeholder="Search by name or code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="border rounded-lg px-3 py-2"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s || 'All statuses'}
            </option>
          ))}
        </select>
      </div>

      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">Error: {error}</p>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((project) => (
          <div
            key={project.id}
            className={`rounded-xl border p-4 bg-white shadow-sm ${
              isOverdue(project) ? 'border-red-400 ring-1 ring-red-200' : 'border-gray-200'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono text-gray-400">{project.code}</span>
              <StatusBadge status={isOverdue(project) ? 'overdue' : project.status} />
            </div>
            <h3 className="font-semibold text-gray-900">{project.name}</h3>
            <p className="text-sm text-gray-500 mt-1">
              👷 {project.current_team || '—'}
              {project.location ? ` · 📍 ${project.location}` : ''}
            </p>
            {project.opening_date && (
              <p className="text-sm mt-1 text-gray-500">🏬 Opens: {project.opening_date}</p>
            )}
          </div>
        ))}
        {!loading && filtered.length === 0 && <p className="text-gray-500">No projects found.</p>}
      </div>
    </div>
  );
}
