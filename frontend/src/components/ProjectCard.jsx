// ProjectCard.jsx — summary card for a single project. Shows name, code, status
// badge, progress bar, current stage, days remaining and the assigned team.
import { Link } from 'react-router-dom';
import StatusBadge from './StatusBadge';
import ProgressBar from './ProgressBar';
import { isOverdue, projectHealth, stageProgress, statusLabel } from '../utils/status';
import { daysRemainingLabel } from '../utils/date';
import { useTheme } from '../context/ThemeContext';

export default function ProjectCard({ project, selectable, selected, onSelect }) {
  const { locale } = useTheme();
  const health = projectHealth(project);
  const overdue = isOverdue(project);
  const progress = stageProgress(project);

  return (
    <div
      className={`card p-4 transition hover:shadow-md ${
        overdue ? 'ring-1 ring-red-300' : ''
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {selectable && (
            <input
              type="checkbox"
              checked={selected}
              onChange={(e) => onSelect?.(project.id, e.target.checked)}
              aria-label={`Select ${project.name}`}
            />
          )}
          <span className="font-mono text-xs text-gray-400">{project.code}</span>
        </div>
        <StatusBadge status={overdue ? 'overdue' : project.status} />
      </div>

      <Link
        to={`/projects/${encodeURIComponent(project.code)}`}
        className="block font-semibold text-gray-900 hover:text-brand-green dark:text-gray-100"
      >
        {project.name}
      </Link>

      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
        {statusLabel(project.status, locale)}
        {project.current_team ? ` · 👷 ${project.current_team}` : ''}
        {project.location ? ` · 📍 ${project.location}` : ''}
      </p>

      <div className="mt-3">
        <ProgressBar value={progress} health={health} />
      </div>

      {project.opening_date && (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          🏬 {daysRemainingLabel(project.opening_date, locale)}
        </p>
      )}
    </div>
  );
}
