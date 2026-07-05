// Dashboard.jsx — overview: stat cards, AI insights, recent activity, quick
// actions, a weekly project chart and a team workload heatmap.
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import StatCard from '../components/StatCard';
import AISuggestionCard from '../components/AISuggestionCard';
import Chart from '../components/Chart';
import Loading from '../components/Loading';
import TeamMember from '../components/TeamMember';
import { useProjects } from '../hooks/useProjects';
import { useInsights } from '../hooks/useAnalytics';
import { useWebSocket } from '../hooks/useWebSocket';
import { projectHealth } from '../utils/status';
import { timeAgo } from '../utils/date';
import { BRAND } from '../styles/themes';
import { useTheme } from '../context/ThemeContext';

export default function Dashboard() {
  const { locale } = useTheme();
  const { data: projects = [], isLoading } = useProjects();
  const { data: insights = [] } = useInsights();
  useWebSocket('projects', ['projects']);

  const stats = useMemo(() => {
    const counts = { active: 0, on_track: 0, at_risk: 0, delayed: 0 };
    for (const p of projects) {
      if (p.status !== 'completed') counts.active += 1;
      const h = projectHealth(p);
      if (h === 'on_track') counts.on_track += 1;
      else if (h === 'at_risk') counts.at_risk += 1;
      else if (h === 'delayed') counts.delayed += 1;
    }
    return counts;
  }, [projects]);

  // Weekly chart: projects created per weekday.
  const weeklyChart = useMemo(() => {
    const labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const buckets = new Array(7).fill(0);
    for (const p of projects) {
      if (p.created_at) buckets[new Date(p.created_at).getDay()] += 1;
    }
    return {
      labels,
      datasets: [{ label: locale === 'ar' ? 'مشاريع' : 'Projects', data: buckets, backgroundColor: BRAND.green }],
    };
  }, [projects, locale]);

  // Team workload heatmap: number of active projects per current team.
  const workload = useMemo(() => {
    const map = {};
    for (const p of projects) {
      if (p.status === 'completed') continue;
      const team = p.current_team || '—';
      map[team] = (map[team] || 0) + 1;
    }
    const max = Math.max(1, ...Object.values(map));
    return { entries: Object.entries(map), max };
  }, [projects]);

  const recent = useMemo(
    () =>
      [...projects]
        .filter((p) => p.updated_at || p.created_at)
        .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at))
        .slice(0, 6),
    [projects],
  );

  if (isLoading) return <Loading />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-brand-green dark:text-brand-gold">
          لوحة التحكم / Dashboard
        </h1>
        <div className="flex gap-2">
          <Link to="/projects" className="btn-primary">➕ مشروع جديد / New Project</Link>
          <Link to="/teams" className="btn-gold">👥 إضافة فريق / Add Team</Link>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="المشاريع النشطة / Active Projects" value={stats.active} icon="🏬" />
        <StatCard label="على المسار / On Track" value={stats.on_track} icon="✅" accent="green" />
        <StatCard label="في خطر / At Risk" value={stats.at_risk} icon="⚠️" accent="amber" />
        <StatCard label="متأخرة / Delayed" value={stats.delayed} icon="⛔" accent="red" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Weekly chart */}
        <div className="card p-4 lg:col-span-2">
          <h2 className="mb-3 font-semibold">المشاريع الأسبوعية / Weekly Projects</h2>
          <Chart type="bar" data={weeklyChart} options={{ legend: false }} />
        </div>

        {/* AI insights */}
        <div className="space-y-3">
          <h2 className="font-semibold">رؤى الذكاء الاصطناعي / AI Insights</h2>
          {insights.length === 0 && (
            <p className="text-sm text-gray-400">لا توجد اقتراحات بعد / No suggestions yet.</p>
          )}
          {insights.slice(0, 3).map((ins) => (
            <AISuggestionCard
              key={ins.id}
              title={ins.title || 'Insight'}
              description={ins.description || ins.message}
              confidence={ins.confidence}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent activity */}
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">النشاط الأخير / Recent Activity</h2>
          <ul className="space-y-2">
            {recent.map((p) => (
              <li key={p.id} className="flex items-center justify-between text-sm">
                <Link to={`/projects/${encodeURIComponent(p.code)}`} className="hover:text-brand-green">
                  <span className="font-mono text-xs text-gray-400">{p.code}</span> {p.name}
                </Link>
                <span className="text-xs text-gray-400">{timeAgo(p.updated_at || p.created_at, locale)}</span>
              </li>
            ))}
            {recent.length === 0 && <li className="text-sm text-gray-400">No activity.</li>}
          </ul>
        </div>

        {/* Team workload heatmap */}
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">حِمل العمل للفِرق / Team Workload</h2>
          <div className="space-y-2">
            {workload.entries.map(([team, count]) => (
              <div key={team} className="flex items-center gap-2">
                <TeamMember name={team} size="sm" />
                <div className="flex-1">
                  <div className="h-4 rounded bg-gray-100 dark:bg-white/10">
                    <div
                      className="h-4 rounded bg-brand-greenLight"
                      style={{ width: `${(count / workload.max) * 100}%` }}
                    />
                  </div>
                </div>
                <span className="w-6 text-right text-sm">{count}</span>
              </div>
            ))}
            {workload.entries.length === 0 && <p className="text-sm text-gray-400">No active teams.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
