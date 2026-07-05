// ProjectDetail.jsx — detailed project view: stage timeline, per-stage team
// progress, task list, communication log, escalation history, AI recommendations
// and actions (complete stage / add task / escalate).
import { useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import StatusBadge from '../components/StatusBadge';
import StageTimeline from '../components/StageTimeline';
import ProgressBar from '../components/ProgressBar';
import AISuggestionCard from '../components/AISuggestionCard';
import Modal from '../components/Modal';
import Loading from '../components/Loading';
import { useProject, useUpdateProject, useAddTask } from '../hooks/useProjects';
import { useWebSocket } from '../hooks/useWebSocket';
import { useNotifications } from '../hooks/useNotifications';
import { PROJECT_STAGES, stageProgress, projectHealth } from '../utils/status';
import { formatDateTime } from '../utils/date';
import { required } from '../utils/validators';
import { useTheme } from '../context/ThemeContext';

export default function ProjectDetail() {
  const { id } = useParams();
  const { locale } = useTheme();
  const { data, isLoading, error: loadError } = useProject(id);
  const updateProject = useUpdateProject();
  const addTask = useAddTask();
  const { success, error } = useNotifications();
  useWebSocket('tasks', ['project', id]);

  const [showTask, setShowTask] = useState(false);
  const [showEscalate, setShowEscalate] = useState(false);
  const { register, handleSubmit, reset, formState: { errors } } = useForm();
  const escalateForm = useForm();

  const project = data?.project;
  const tasks = data?.tasks || [];
  const logs = data?.logs || [];

  const stages = useMemo(() => {
    const wf = project?.metadata?.workflow;
    return wf ? [...wf.map((t) => `${t}_pending`), 'ready', 'completed'] : PROJECT_STAGES;
  }, [project]);

  const taskCounts = useMemo(() => {
    const map = {};
    for (const t of tasks) {
      const key = `${t.assigned_team}_pending`;
      if (!map[key]) map[key] = { done: 0, total: 0 };
      map[key].total += 1;
      if (t.status === 'done') map[key].done += 1;
    }
    return map;
  }, [tasks]);

  const escalations = useMemo(() => logs.filter((l) => /escalat/i.test(l.message || '')), [logs]);

  if (isLoading) return <Loading />;
  if (loadError || !project)
    return (
      <div>
        <p className="text-red-600">تعذر تحميل المشروع / Could not load project.</p>
        <Link to="/projects" className="text-brand-green underline">
          ← العودة / Back to projects
        </Link>
      </div>
    );

  const completeStage = async () => {
    const idx = stages.indexOf(project.status);
    const next = stages[Math.min(idx + 1, stages.length - 1)];
    try {
      await updateProject.mutateAsync({ id: project.id, patch: { status: next } });
      success(locale === 'ar' ? 'تم إكمال المرحلة' : 'Stage completed');
    } catch (e) {
      error(e.message);
    }
  };

  const onAddTask = async (values) => {
    try {
      await addTask.mutateAsync({ projectId: project.id, task: values });
      success(locale === 'ar' ? 'تمت إضافة المهمة' : 'Task added');
      setShowTask(false);
      reset();
    } catch (e) {
      error(e.message);
    }
  };

  const onEscalate = async (values) => {
    try {
      await updateProject.mutateAsync({
        id: project.id,
        patch: { metadata: { ...(project.metadata || {}), last_escalation: values.reason } },
      });
      success(locale === 'ar' ? 'تم التصعيد' : 'Escalated');
      setShowEscalate(false);
      escalateForm.reset();
    } catch (e) {
      error(e.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/projects" className="text-sm text-gray-400 hover:text-brand-green">
            ← المشاريع / Projects
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-brand-green dark:text-brand-gold">
            {project.name} <span className="font-mono text-sm text-gray-400">{project.code}</span>
          </h1>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={completeStage} disabled={project.status === 'completed'}>
            ✅ إكمال المرحلة / Complete stage
          </button>
          <button className="btn-gold" onClick={() => setShowTask(true)}>
            ➕ مهمة / Add task
          </button>
          <button className="btn-outline" onClick={() => setShowEscalate(true)}>
            🚨 تصعيد / Escalate
          </button>
        </div>
      </div>

      <div className="card p-4">
        <div className="mb-4 flex items-center justify-between">
          <StatusBadge status={project.status} />
          <span className="text-sm text-gray-400">
            {formatDateTime(project.opening_date, locale)}
          </span>
        </div>
        <ProgressBar value={stageProgress(project)} health={projectHealth(project)} />
        <div className="mt-6">
          <StageTimeline stages={stages} current={project.status} taskCounts={taskCounts} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Task list */}
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">المهام / Tasks</h2>
          <ul className="space-y-2">
            {tasks.map((t) => (
              <li key={t.id} className="flex items-center justify-between rounded-lg border border-gray-100 p-2 dark:border-white/10">
                <div>
                  <div className="text-sm">{t.description}</div>
                  <div className="text-xs capitalize text-gray-400">
                    {t.assigned_team}
                    {t.deadline ? ` · 🗓️ ${t.deadline}` : ''}
                  </div>
                </div>
                <StatusBadge status={t.status} />
              </li>
            ))}
            {tasks.length === 0 && <li className="text-sm text-gray-400">لا توجد مهام / No tasks.</li>}
          </ul>
        </div>

        {/* Communication log */}
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">سجل التواصل / Communication Log</h2>
          <ul className="space-y-2">
            {logs.map((l) => (
              <li key={l.id} className="text-sm">
                <span className="text-xs text-gray-400">{formatDateTime(l.created_at, locale)}</span>
                <div>{l.message}</div>
              </li>
            ))}
            {logs.length === 0 && <li className="text-sm text-gray-400">No messages.</li>}
          </ul>
        </div>

        {/* Escalation history */}
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">سجل التصعيد / Escalation History</h2>
          <ul className="space-y-2">
            {escalations.map((l) => (
              <li key={l.id} className="rounded-lg bg-red-50 p-2 text-sm text-red-800 dark:bg-red-900/30 dark:text-red-200">
                <span className="text-xs opacity-70">{formatDateTime(l.created_at, locale)}</span>
                <div>{l.message}</div>
              </li>
            ))}
            {escalations.length === 0 && <li className="text-sm text-gray-400">No escalations.</li>}
          </ul>
        </div>

        {/* AI recommendations */}
        <div className="space-y-3">
          <h2 className="font-semibold">توصيات الذكاء الاصطناعي / AI Recommendations</h2>
          <AISuggestionCard
            title={locale === 'ar' ? 'توصية' : 'Recommendation'}
            description={
              projectHealth(project) === 'delayed'
                ? locale === 'ar'
                  ? 'المشروع متأخر — يُنصح بالتصعيد للفريق المسؤول.'
                  : 'Project is delayed — consider escalating to the responsible team.'
                : locale === 'ar'
                ? 'المشروع يسير على ما يرام. تابع المهام المفتوحة.'
                : 'Project is on track. Keep monitoring open tasks.'
            }
            confidence={0.82}
          />
        </div>
      </div>

      {/* Add task modal */}
      <Modal
        open={showTask}
        onClose={() => setShowTask(false)}
        title={locale === 'ar' ? 'إضافة مهمة' : 'Add Task'}
        footer={
          <>
            <button className="btn-outline" onClick={() => setShowTask(false)}>إلغاء / Cancel</button>
            <button className="btn-primary" onClick={handleSubmit(onAddTask)}>إضافة / Add</button>
          </>
        }
      >
        <form className="space-y-3" onSubmit={handleSubmit(onAddTask)}>
          <label className="block">
            <span className="text-sm font-medium">الوصف / Description</span>
            <input className="input mt-1 w-full" {...register('description', { validate: required })} />
            {errors.description && <span className="text-xs text-red-600">{errors.description.message}</span>}
          </label>
          <label className="block">
            <span className="text-sm font-medium">الفريق / Team</span>
            <input className="input mt-1 w-full" placeholder="marketing" {...register('assigned_team')} />
          </label>
          <label className="block">
            <span className="text-sm font-medium">الموعد النهائي / Deadline</span>
            <input type="date" className="input mt-1 w-full" {...register('deadline')} />
          </label>
        </form>
      </Modal>

      {/* Escalate modal */}
      <Modal
        open={showEscalate}
        onClose={() => setShowEscalate(false)}
        title={locale === 'ar' ? 'تصعيد' : 'Escalate'}
        footer={
          <>
            <button className="btn-outline" onClick={() => setShowEscalate(false)}>إلغاء / Cancel</button>
            <button className="btn-primary" onClick={escalateForm.handleSubmit(onEscalate)}>تصعيد / Escalate</button>
          </>
        }
      >
        <label className="block">
          <span className="text-sm font-medium">السبب / Reason</span>
          <textarea className="input mt-1 w-full" rows={3} {...escalateForm.register('reason', { validate: required })} />
          {escalateForm.formState.errors.reason && (
            <span className="text-xs text-red-600">{escalateForm.formState.errors.reason.message}</span>
          )}
        </label>
      </Modal>
    </div>
  );
}
