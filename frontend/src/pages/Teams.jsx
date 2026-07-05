// Teams.jsx — team management: team cards (members, workload, skills), add/edit
// team lead, availability settings and per-team performance metrics.
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import TeamMember from '../components/TeamMember';
import Modal from '../components/Modal';
import Loading from '../components/Loading';
import ProgressBar from '../components/ProgressBar';
import { useTeams, useUpsertTeam } from '../hooks/useTeams';
import { useProjects } from '../hooks/useProjects';
import { useNotifications } from '../hooks/useNotifications';
import { required, isPhone, compose } from '../utils/validators';
import { titleCase } from '../utils/formatting';
import { useTheme } from '../context/ThemeContext';

export default function Teams() {
  const { locale } = useTheme();
  const { data: teams = [], isLoading } = useTeams();
  const { data: projects = [] } = useProjects();
  const upsertTeam = useUpsertTeam();
  const { success, error } = useNotifications();

  const [editing, setEditing] = useState(null); // team object or {} for new
  const { register, handleSubmit, reset, formState: { errors } } = useForm();

  const openEditor = (team) => {
    setEditing(team || {});
    reset(team || { team_name: '', whatsapp_number: '', escalation_number: '' });
  };

  const workloadFor = (teamName) =>
    projects.filter((p) => p.status !== 'completed' && p.current_team === teamName).length;

  const onSave = async (values) => {
    try {
      await upsertTeam.mutateAsync(values);
      success(locale === 'ar' ? 'تم حفظ الفريق' : 'Team saved');
      setEditing(null);
    } catch (e) {
      error(e.message);
    }
  };

  if (isLoading) return <Loading />;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-brand-green dark:text-brand-gold">الفِرق / Teams</h1>
        <button className="btn-primary" onClick={() => openEditor(null)}>
          ➕ إضافة فريق / Add Team
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {teams.map((team) => {
          const load = workloadFor(team.team_name);
          const skills = team.skills || [];
          return (
            <div key={team.id || team.team_name} className="card p-4">
              <div className="mb-3 flex items-center justify-between">
                <TeamMember name={team.name || titleCase(team.team_name)} role={team.team_name} />
                <button className="text-sm text-brand-green hover:underline" onClick={() => openEditor(team)}>
                  ✏️ تعديل / Edit
                </button>
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">
                📱 {team.whatsapp_number || '—'}
              </div>
              {team.escalation_number && (
                <div className="text-sm text-gray-500 dark:text-gray-400">🚨 {team.escalation_number}</div>
              )}

              <div className="mt-3">
                <div className="mb-1 text-xs text-gray-400">
                  حِمل العمل / Workload: {load} {locale === 'ar' ? 'مشروع' : 'projects'}
                </div>
                <ProgressBar
                  value={Math.min(100, load * 25)}
                  health={load > 3 ? 'delayed' : load > 1 ? 'at_risk' : 'on_track'}
                  showLabel={false}
                />
              </div>

              {skills.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {skills.map((s) => (
                    <span key={s} className="badge bg-brand-green/10 text-brand-green dark:text-brand-gold">
                      {s}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-3 flex items-center justify-between text-xs text-gray-400">
                <span>الأداء / Performance</span>
                <span className="font-semibold text-brand-green dark:text-brand-gold">
                  {team.performance ?? '—'}
                </span>
              </div>
            </div>
          );
        })}
        {teams.length === 0 && <p className="text-gray-500">لا توجد فِرق / No teams yet.</p>}
      </div>

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.id ? (locale === 'ar' ? 'تعديل الفريق' : 'Edit Team') : locale === 'ar' ? 'فريق جديد' : 'New Team'}
        footer={
          <>
            <button className="btn-outline" onClick={() => setEditing(null)}>إلغاء / Cancel</button>
            <button className="btn-primary" onClick={handleSubmit(onSave)} disabled={upsertTeam.isPending}>
              حفظ / Save
            </button>
          </>
        }
      >
        <form className="space-y-3" onSubmit={handleSubmit(onSave)}>
          <label className="block">
            <span className="text-sm font-medium">اسم القائد / Lead name</span>
            <input className="input mt-1 w-full" {...register('name')} />
          </label>
          <label className="block">
            <span className="text-sm font-medium">اسم الفريق / Team name</span>
            <input className="input mt-1 w-full" placeholder="marketing" {...register('team_name', { validate: required })} />
            {errors.team_name && <span className="text-xs text-red-600">{errors.team_name.message}</span>}
          </label>
          <label className="block">
            <span className="text-sm font-medium">رقم واتساب / WhatsApp number</span>
            <input
              className="input mt-1 w-full"
              placeholder="+9665XXXXXXXX"
              {...register('whatsapp_number', { validate: compose(required, isPhone) })}
            />
            {errors.whatsapp_number && <span className="text-xs text-red-600">{errors.whatsapp_number.message}</span>}
          </label>
          <label className="block">
            <span className="text-sm font-medium">رقم التصعيد / Escalation number</span>
            <input
              className="input mt-1 w-full"
              placeholder="+9665XXXXXXXX"
              {...register('escalation_number', { validate: isPhone })}
            />
            {errors.escalation_number && <span className="text-xs text-red-600">{errors.escalation_number.message}</span>}
          </label>
        </form>
      </Modal>
    </div>
  );
}
