// App.jsx — application shell: sidebar + header layout with routed pages, guarded
// by authentication. Renders the Login screen when the user is not signed in.
import { useState } from 'react';
import { Route, Routes, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import Toast from './components/Toast';
import Loading from './components/Loading';
import Dashboard from './pages/Dashboard';
import Projects from './pages/Projects';
import ProjectDetail from './pages/ProjectDetail';
import Workflows from './pages/Workflows';
import Teams from './pages/Teams';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import WhatsAppSettings from './pages/WhatsAppSettings';
import Login from './pages/Login';
import { useAuth } from './hooks/useAuth';

export default function App() {
  const { isAuthenticated, loading } = useAuth();
  const [navOpen, setNavOpen] = useState(false);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loading />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <>
        <Login />
        <Toast />
      </>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />
      {/* Mobile backdrop when the sidebar is open. */}
      {navOpen && (
        <div className="fixed inset-0 z-20 bg-black/40 md:hidden" onClick={() => setNavOpen(false)} aria-hidden="true" />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenu={() => setNavOpen((o) => !o)} />
        <main className="flex-1 overflow-auto bg-gray-50 p-6 dark:bg-brand-greenDark">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/teams" element={<Teams />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/whatsapp" element={<WhatsAppSettings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      <Toast />
    </div>
  );
}
