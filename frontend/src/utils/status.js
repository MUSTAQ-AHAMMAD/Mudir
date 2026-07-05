// status.js — helpers for project/task status: normalisation, labels (AR/EN),
// health classification and derived progress. Backend states from the state
// machine: property_pending → marketing_pending → it_pending → ready → completed.

export const PROJECT_STAGES = [
  'property_pending',
  'marketing_pending',
  'it_pending',
  'ready',
  'completed',
];

// Bilingual labels for every status we display.
const LABELS = {
  property_pending: { ar: 'العقارات', en: 'Property' },
  marketing_pending: { ar: 'التسويق', en: 'Marketing' },
  it_pending: { ar: 'تقنية المعلومات', en: 'IT' },
  ready: { ar: 'جاهز', en: 'Ready' },
  completed: { ar: 'مكتمل', en: 'Completed' },
  overdue: { ar: 'متأخر', en: 'Overdue' },
  on_track: { ar: 'على المسار', en: 'On Track' },
  at_risk: { ar: 'في خطر', en: 'At Risk' },
  delayed: { ar: 'متأخر', en: 'Delayed' },
  done: { ar: 'تم', en: 'Done' },
  in_progress: { ar: 'قيد التنفيذ', en: 'In Progress' },
  pending: { ar: 'معلّق', en: 'Pending' },
  blocked: { ar: 'محظور', en: 'Blocked' },
  active: { ar: 'نشط', en: 'Active' },
};

/** Human label for a status, defaulting to the raw key. */
export function statusLabel(status, locale = 'ar') {
  const entry = LABELS[status];
  if (!entry) return status || '—';
  return entry[locale] || entry.en;
}

/** Is a project past its opening date without being completed? */
export function isOverdue(project) {
  if (!project?.opening_date || project.status === 'completed') return false;
  return new Date(project.opening_date) < new Date();
}

/**
 * Health classification used by dashboard stat cards and badges.
 * Returns one of: 'completed' | 'delayed' | 'at_risk' | 'on_track'.
 */
export function projectHealth(project) {
  if (!project) return 'on_track';
  if (project.status === 'completed') return 'completed';
  if (isOverdue(project)) return 'delayed';
  const days = daysUntil(project.opening_date);
  if (days !== null && days <= 3) return 'at_risk';
  return 'on_track';
}

function daysUntil(value) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((d.getTime() - Date.now()) / 86_400_000);
}

/** Progress (0-100) derived from the project's stage in the workflow. */
export function stageProgress(project) {
  if (!project) return 0;
  if (project.status === 'completed') return 100;
  const workflow = project.metadata?.workflow;
  const stages = workflow
    ? [...workflow.map((t) => `${t}_pending`), 'ready', 'completed']
    : PROJECT_STAGES;
  const idx = stages.indexOf(project.status);
  if (idx < 0) return 0;
  return Math.round((idx / (stages.length - 1)) * 100);
}
