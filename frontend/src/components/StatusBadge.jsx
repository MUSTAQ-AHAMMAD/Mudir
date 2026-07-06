// StatusBadge.jsx — colour-coded status badge with bilingual label.
import { badgeClass } from '../utils/colors';
import { statusLabel } from '../utils/status';
import { useTheme } from '../context/ThemeContext';

export default function StatusBadge({ status, label }) {
  const { locale } = useTheme();
  return (
    <span className={`badge ${badgeClass(status)}`}>{label || statusLabel(status, locale)}</span>
  );
}
