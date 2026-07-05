// Workflows.jsx — workflow management: list existing workflows, a simple
// drag-and-drop stage builder, AI-discovered workflows with accept/reject, and
// export/import of workflow definitions (JSON).
import { useState } from 'react';
import AISuggestionCard from '../components/AISuggestionCard';
import Loading from '../components/Loading';
import StatusBadge from '../components/StatusBadge';
import { useWorkflows, useWorkflowSuggestions, useSaveWorkflow, useResolveSuggestion } from '../hooks/useWorkflows';
import { useNotifications } from '../hooks/useNotifications';
import { exportJSON, importJSONFile } from '../utils/export';
import { useTheme } from '../context/ThemeContext';

export default function Workflows() {
  const { locale } = useTheme();
  const { data: workflows = [], isLoading } = useWorkflows();
  const { data: suggestions = [] } = useWorkflowSuggestions();
  const saveWorkflow = useSaveWorkflow();
  const resolve = useResolveSuggestion();
  const { success, error } = useNotifications();

  const [name, setName] = useState('');
  const [stages, setStages] = useState(['property', 'marketing', 'it']);
  const [dragIndex, setDragIndex] = useState(null);

  const addStage = () => setStages((prev) => [...prev, `stage_${prev.length + 1}`]);
  const updateStage = (i, value) => setStages((prev) => prev.map((s, idx) => (idx === i ? value : s)));
  const removeStage = (i) => setStages((prev) => prev.filter((_, idx) => idx !== i));

  // Drag-and-drop reordering of stages.
  const onDrop = (i) => {
    if (dragIndex === null || dragIndex === i) return;
    setStages((prev) => {
      const next = [...prev];
      const [moved] = next.splice(dragIndex, 1);
      next.splice(i, 0, moved);
      return next;
    });
    setDragIndex(null);
  };

  const save = async () => {
    if (!name.trim()) return error(locale === 'ar' ? 'أدخل اسمًا' : 'Enter a name');
    try {
      await saveWorkflow.mutateAsync({ name: name.trim(), stages });
      success(locale === 'ar' ? 'تم حفظ مسار العمل' : 'Workflow saved');
      setName('');
    } catch (e) {
      error(e.message);
    }
  };

  const onImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const wf = await importJSONFile(file);
      setName(wf.name || '');
      setStages(Array.isArray(wf.stages) ? wf.stages : stages);
      success(locale === 'ar' ? 'تم الاستيراد' : 'Imported');
    } catch (err) {
      error(err.message);
    }
    e.target.value = '';
  };

  const resolveSuggestion = async (id, accepted) => {
    try {
      await resolve.mutateAsync({ id, accepted });
      success(accepted ? (locale === 'ar' ? 'تم القبول' : 'Accepted') : locale === 'ar' ? 'تم الرفض' : 'Rejected');
    } catch (e) {
      error(e.message);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-brand-green dark:text-brand-gold">
        مسارات العمل / Workflows
      </h1>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Builder */}
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">منشئ مسار العمل / Workflow Builder</h2>
          <input
            className="input mb-3 w-full"
            placeholder={locale === 'ar' ? 'اسم مسار العمل' : 'Workflow name'}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <ul className="space-y-2">
            {stages.map((stage, i) => (
              <li
                key={i}
                draggable
                onDragStart={() => setDragIndex(i)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(i)}
                className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-2 dark:border-white/10 dark:bg-white/5"
              >
                <span className="cursor-grab text-gray-400" aria-hidden="true">⠿</span>
                <input
                  className="input flex-1"
                  value={stage}
                  onChange={(e) => updateStage(i, e.target.value)}
                  aria-label={`Stage ${i + 1}`}
                />
                <button className="text-sm text-red-600" onClick={() => removeStage(i)}>✕</button>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-outline" onClick={addStage}>➕ مرحلة / Add stage</button>
            <button className="btn-primary" onClick={save} disabled={saveWorkflow.isPending}>
              💾 حفظ / Save
            </button>
            <button className="btn-outline" onClick={() => exportJSON({ name, stages }, `${name || 'workflow'}.json`)}>
              ⬇️ تصدير / Export
            </button>
            <label className="btn-outline cursor-pointer">
              ⬆️ استيراد / Import
              <input type="file" accept="application/json" className="hidden" onChange={onImport} />
            </label>
          </div>
        </div>

        {/* AI-discovered workflows */}
        <div className="space-y-3">
          <h2 className="font-semibold">مسارات مكتشفة بالذكاء الاصطناعي / AI-Discovered</h2>
          {suggestions.length === 0 && (
            <p className="text-sm text-gray-400">لا توجد اقتراحات / No suggestions.</p>
          )}
          {suggestions.map((s) => (
            <AISuggestionCard
              key={s.id}
              title={s.name || 'Discovered workflow'}
              description={Array.isArray(s.stages) ? s.stages.join(' → ') : s.description}
              confidence={s.confidence}
              accepted={s.status === 'accepted'}
              onAccept={() => resolveSuggestion(s.id, true)}
              onReject={() => resolveSuggestion(s.id, false)}
            />
          ))}
        </div>
      </div>

      {/* Existing workflows */}
      <div className="card p-4">
        <h2 className="mb-3 font-semibold">مسارات العمل الحالية / Existing Workflows</h2>
        {isLoading ? (
          <Loading />
        ) : (
          <ul className="space-y-2">
            {workflows.map((wf) => (
              <li key={wf.id || wf.name} className="flex items-center justify-between rounded-lg border border-gray-100 p-3 dark:border-white/10">
                <div>
                  <div className="font-medium">{wf.name}</div>
                  <div className="text-xs text-gray-400">
                    {Array.isArray(wf.stages) ? wf.stages.join(' → ') : ''}
                  </div>
                </div>
                <StatusBadge status={wf.status || 'active'} />
              </li>
            ))}
            {workflows.length === 0 && <li className="text-sm text-gray-400">No workflows yet.</li>}
          </ul>
        )}
      </div>
    </div>
  );
}
