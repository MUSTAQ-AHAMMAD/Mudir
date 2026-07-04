// App.jsx — layout shell with the left sidebar navigation and routed pages.
import { NavLink, Route, Routes, Navigate } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import ProjectTimeline from './components/ProjectTimeline';
import TeamOnboarding from './components/TeamOnboarding';
import Analytics from './components/Analytics';
import Settings from './components/Settings';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '📊' },
  { to: '/timeline', label: 'Timeline', icon: '🗓️' },
  { to: '/onboarding', label: 'Teams', icon: '👥' },
  { to: '/analytics', label: 'Analytics', icon: '📈' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
];

export default function App() {
  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 bg-brand-green text-white flex flex-col print:hidden">
        <div className="px-4 py-5 flex items-center gap-2 border-b border-white/10">
          <span className="text-2xl">🌙</span>
          <div>
            <div className="font-bold text-brand-gold">مدير</div>
            <div className="text-xs -mt-0.5">Mudir</div>
          </div>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
                  isActive ? 'bg-white/15 text-brand-gold' : 'hover:bg-white/10'
                }`
              }
            >
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 text-xs text-white/50">AI Project Coordinator</div>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/timeline" element={<ProjectTimeline />} />
          <Route path="/onboarding" element={<TeamOnboarding />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
