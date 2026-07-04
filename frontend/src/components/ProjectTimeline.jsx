// ProjectTimeline.jsx — per-team columns showing task progress for a project.
// Pick a project, then see Property / Marketing / IT columns with their tasks.
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import StatusBadge from './StatusBadge';

export default function ProjectTimeline() {
  const [projects, setProjects] = useState([]);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  // Load the project list once for the selector.
  useEffect(() => {
    api
      .listProjects()
      .then((data) => {
        setProjects(data.projects || []);
        if (data.projects && data.projects[0]) setSelected(data.projects[0].code);
      })
      .catch((e) => setError(e.message));
  }, []);

  // Load the selected project's tasks + logs.
  useEffect(() => {
    if (!selected) return;
    api
      .getProject(selected)
      .then(setDetail)
      .catch((e) => setError(e.message));
  }, [selected]);

  // Group tasks by team, respecting the project's custom workflow order.
  const workflow = detail?.project?.metadata?.workflow || ['property', 'marketing', 'it'];
  const tasksByTeam = (team) => (detail?.tasks || []).filter((t) => t.assigned_team === team);

  return (
    <div>
      <h1 className="text-2xl font-bold text-brand-green mb-4">الجدول الزمني / Timeline</h1>

      <select
        className="border rounded-lg px-3 py-2 mb-6"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
      >
        {projects.map((p) => (
          <option key={p.id} value={p.code}>
            {p.code} — {p.name}
          </option>
        ))}
      </select>

      {error && <p className="text-red-600">Error: {error}</p>}

      {detail && (
        <>
          {detail.project.status === 'ready' && (
            <div className="mb-4 rounded-lg bg-green-600 text-white px-4 py-3 font-semibold">
              🎉 Store Opens On Time — all teams ready!
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-3">
            {workflow.map((team) => (
              <div key={team} className="rounded-xl border border-gray-200 bg-white p-4">
                <h3 className="font-semibold capitalize mb-3 text-brand-greenLight">{team}</h3>
                <div className="space-y-2">
                  {tasksByTeam(team).map((task) => (
                    <div key={task.id} className="rounded-lg border border-gray-100 p-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">{task.description}</span>
                        <StatusBadge status={task.status} />
                      </div>
                      {task.deadline && (
                        <span className="text-xs text-gray-400">🗓️ {task.deadline}</span>
                      )}
                    </div>
                  ))}
                  {tasksByTeam(team).length === 0 && (
                    <p className="text-xs text-gray-400">No tasks.</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
