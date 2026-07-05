// AISuggestionCard.jsx — AI recommendation / discovered-workflow card with an
// optional confidence score and accept/reject actions.
import { formatPercent } from '../utils/formatting';
import { useTheme } from '../context/ThemeContext';

export default function AISuggestionCard({
  title,
  description,
  confidence,
  onAccept,
  onReject,
  accepted,
}) {
  const { locale } = useTheme();
  return (
    <div className="card border-l-4 border-brand-gold p-4 rtl:border-l-0 rtl:border-r-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span aria-hidden="true">🤖</span>
          <h3 className="font-semibold text-brand-green dark:text-brand-gold">{title}</h3>
        </div>
        {confidence != null && (
          <span className="badge bg-brand-gold/20 text-brand-green dark:text-brand-gold">
            {formatPercent(confidence, locale, { fromFraction: confidence <= 1 })}
          </span>
        )}
      </div>
      {description && <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{description}</p>}
      {(onAccept || onReject) && (
        <div className="mt-3 flex gap-2">
          <button className="btn-primary px-3 py-1" onClick={onAccept} disabled={accepted}>
            {accepted ? 'مقبول / Accepted' : 'قبول / Accept'}
          </button>
          <button className="btn-outline px-3 py-1" onClick={onReject}>
            رفض / Reject
          </button>
        </div>
      )}
    </div>
  );
}
