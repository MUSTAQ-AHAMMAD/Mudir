// Sidebar.jsx — primary navigation. Collapsible on mobile via the `open` prop.
import { NavLink } from 'react-router-dom';
import { useTheme } from '../context/ThemeContext';

const NAV = [
  { to: '/', label: { ar: 'الرئيسية', en: 'Dashboard' }, icon: '📊', end: true },
  { to: '/projects', label: { ar: 'المشاريع', en: 'Projects' }, icon: '🏬' },
  { to: '/workflows', label: { ar: 'مسارات العمل', en: 'Workflows' }, icon: '🔀' },
  { to: '/teams', label: { ar: 'الفِرق', en: 'Teams' }, icon: '👥' },
  { to: '/analytics', label: { ar: 'التحليلات', en: 'Analytics' }, icon: '📈' },
  { to: '/whatsapp', label: { ar: 'واتساب', en: 'WhatsApp' }, icon: '💬' },
  { to: '/settings', label: { ar: 'الإعدادات', en: 'Settings' }, icon: '⚙️' },
];

export default function Sidebar({ open, onNavigate }) {
  const { locale } = useTheme();
  return (
    <aside
      className={`fixed inset-y-0 z-30 flex w-56 flex-col bg-brand-green bg-saudi-pattern text-white transition-transform
        ltr:left-0 rtl:right-0 md:static md:translate-x-0 print:hidden
        ${open ? 'translate-x-0' : 'max-md:ltr:-translate-x-full max-md:rtl:translate-x-full'}`}
      aria-label="Main navigation"
    >
      <div className="flex items-center gap-2 border-b border-white/10 px-4 py-5">
        <span className="text-2xl" aria-hidden="true">🌙</span>
        <div>
          <div className="font-bold text-brand-gold">مدير</div>
          <div className="-mt-0.5 text-xs">Mudir</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                isActive ? 'bg-white/15 text-brand-gold' : 'hover:bg-white/10'
              }`
            }
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label[locale] || item.label.en}
          </NavLink>
        ))}
      </nav>
      <div className="p-4 text-xs text-white/50">AI Project Coordinator</div>
    </aside>
  );
}
