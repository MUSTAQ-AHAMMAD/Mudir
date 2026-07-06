// StageTimeline.jsx — Gantt-style horizontal timeline of workflow stages.
// Highlights completed stages, the current stage and pending stages, and can
// show the count of tasks per stage.
import { statusLabel } from '../utils/status';
import { useTheme } from '../context/ThemeContext';

/**
 * @param {string[]} stages ordered workflow stage keys (e.g. ['property_pending', ...]).
 * @param {string} current  the project's current status.
 * @param {Object} [taskCounts] optional map of stageKey → { done, total }.
 */
export default function StageTimeline({ stages = [], current, taskCounts = {} }) {
  const { locale } = useTheme();
  const currentIdx = stages.indexOf(current);

  return (
    <ol className="flex flex-col gap-3 md:flex-row md:items-start md:gap-0">
      {stages.map((stage, idx) => {
        const done = currentIdx > idx || current === 'completed';
        const active = idx === currentIdx;
        const counts = taskCounts[stage];
        return (
          <li key={stage} className="flex flex-1 items-start gap-3 md:flex-col md:items-center md:text-center">
            <div className="flex items-center md:w-full md:flex-col">
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
                  done
                    ? 'bg-brand-green text-white'
                    : active
                    ? 'bg-brand-gold text-brand-greenDark ring-4 ring-brand-gold/30'
                    : 'bg-gray-200 text-gray-500 dark:bg-white/10'
                }`}
                aria-hidden="true"
              >
                {done ? '✓' : idx + 1}
              </span>
              {idx < stages.length - 1 && (
                <span
                  className={`mx-2 hidden h-1 flex-1 rounded md:block ${
                    done ? 'bg-brand-green' : 'bg-gray-200 dark:bg-white/10'
                  }`}
                />
              )}
            </div>
            <div className="md:mt-2">
              <div className={`text-sm font-medium ${active ? 'text-brand-green dark:text-brand-gold' : ''}`}>
                {statusLabel(stage, locale)}
              </div>
              {counts && (
                <div className="text-xs text-gray-400">
                  {counts.done}/{counts.total}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
