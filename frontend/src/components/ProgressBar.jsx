// ProgressBar.jsx — animated, accessible progress bar.
import { healthBarClass } from '../utils/colors';

export default function ProgressBar({ value = 0, health = 'on_track', showLabel = true, className = '' }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className={className}>
      <div
        className="h-2.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-white/10"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full rounded-full ${healthBarClass(health)} animate-progress-fill transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{pct}%</div>}
    </div>
  );
}
