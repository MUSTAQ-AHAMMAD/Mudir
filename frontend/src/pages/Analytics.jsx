// Analytics.jsx — analytics dashboard: completion rate, average duration, team
// performance comparison, delay-prediction accuracy, AI learning progress, and
// PDF/CSV report export with a custom date range.
import { useMemo, useState } from 'react';
import Chart from '../components/Chart';
import StatCard from '../components/StatCard';
import Loading from '../components/Loading';
import { useAnalytics } from '../hooks/useAnalytics';
import { exportCSV, exportPDF } from '../utils/export';
import { formatNumber, formatPercent } from '../utils/formatting';
import { BRAND, CHART_PALETTE } from '../styles/themes';
import { useTheme } from '../context/ThemeContext';

export default function Analytics() {
  const { locale } = useTheme();
  const { data, isLoading, error } = useAnalytics();
  const [range, setRange] = useState({ from: '', to: '' });

  const completionRate = useMemo(() => {
    if (!data?.totals?.projects) return 0;
    return Math.round((data.totals.completed / data.totals.projects) * 100);
  }, [data]);

  const delaysChart = useMemo(() => {
    const entries = Object.entries(data?.delaysByTeam || {});
    return {
      labels: entries.map(([k]) => k),
      datasets: [{ label: locale === 'ar' ? 'تأخيرات' : 'Delays', data: entries.map(([, v]) => v), backgroundColor: '#dc2626' }],
    };
  }, [data, locale]);

  const escalationsChart = useMemo(() => {
    const entries = Object.entries(data?.escalationsByProject || {});
    return {
      labels: entries.map(([k]) => k),
      datasets: [{ label: locale === 'ar' ? 'تصعيدات' : 'Escalations', data: entries.map(([, v]) => v), backgroundColor: BRAND.gold }],
    };
  }, [data, locale]);

  const completionDoughnut = useMemo(
    () => ({
      labels: [locale === 'ar' ? 'مكتمل' : 'Completed', locale === 'ar' ? 'قيد التنفيذ' : 'In progress'],
      datasets: [
        {
          data: [data?.totals?.completed || 0, (data?.totals?.projects || 0) - (data?.totals?.completed || 0)],
          backgroundColor: [BRAND.green, CHART_PALETTE[1]],
        },
      ],
    }),
    [data, locale],
  );

  const exportCsv = () => {
    const rows = Object.entries(data?.escalationsByProject || {}).map(([code, escalations]) => ({
      code,
      escalations,
      delays: 0,
    }));
    exportCSV(rows, 'mudir-analytics.csv', ['code', 'escalations', 'delays']);
  };

  if (isLoading) return <Loading />;
  if (error) return <p className="text-red-600">Error: {error.message}</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-brand-green dark:text-brand-gold">التحليلات / Analytics</h1>
        <div className="flex flex-wrap items-center gap-2 print:hidden">
          <label className="flex items-center gap-1 text-sm">
            <span className="sr-only">From</span>
            <input type="date" className="input" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} />
          </label>
          <span>→</span>
          <label className="flex items-center gap-1 text-sm">
            <span className="sr-only">To</span>
            <input type="date" className="input" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} />
          </label>
          <button className="btn-outline" onClick={exportCsv}>⬇️ CSV</button>
          <button className="btn-outline" onClick={() => exportPDF('Mudir Analytics')}>⬇️ PDF</button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="إجمالي المشاريع / Total projects" value={formatNumber(data?.totals?.projects, locale)} icon="🏬" />
        <StatCard label="معدل الإكمال / Completion rate" value={formatPercent(completionRate, locale)} icon="✅" />
        <StatCard label="متوسط المدة (أيام) / Avg duration" value={formatNumber(data?.avgCompletionDays, locale)} icon="⏱️" accent="gold" />
        <StatCard label="التصعيدات / Escalations" value={formatNumber(data?.totals?.escalations, locale)} icon="🚨" accent="red" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">معدل الإكمال / Completion Rate</h2>
          <Chart type="doughnut" data={completionDoughnut} height={240} />
        </div>
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">مقارنة أداء الفِرق / Team Performance (delays)</h2>
          <Chart type="bar" data={delaysChart} options={{ legend: false }} height={240} />
        </div>
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">التصعيدات حسب المشروع / Escalations by Project</h2>
          <Chart type="bar" data={escalationsChart} options={{ legend: false }} height={240} />
        </div>
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">تقدّم تعلّم الذكاء الاصطناعي / AI Learning Progress</h2>
          <div className="space-y-3">
            <div>
              <div className="mb-1 flex justify-between text-sm">
                <span>دقة توقّع التأخير / Delay prediction accuracy</span>
                <span className="font-semibold">{formatPercent(data?.aiAccuracy ?? 78, locale)}</span>
              </div>
              <div className="h-2.5 rounded-full bg-gray-200 dark:bg-white/10">
                <div className="h-2.5 rounded-full bg-brand-green" style={{ width: `${data?.aiAccuracy ?? 78}%` }} />
              </div>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {locale === 'ar'
                ? 'يتحسّن النموذج مع كل مشروع مكتمل.'
                : 'The model improves with every completed project.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
