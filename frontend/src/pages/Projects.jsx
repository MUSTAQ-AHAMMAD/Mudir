// Projects.jsx — full project list with search, filters, project cards, bulk
// actions and a "create project" modal.
import { useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import ProjectCard from '../components/ProjectCard';
import SearchFilter from '../components/SearchFilter';
import Pagination from '../components/Pagination';
import Modal from '../components/Modal';
import Loading from '../components/Loading';
import { useProjects, useCreateProject } from '../hooks/useProjects';
import { useWebSocket } from '../hooks/useWebSocket';
import { useNotifications } from '../hooks/useNotifications';
import { PROJECT_STAGES, statusLabel, isOverdue } from '../utils/status';
import { required, notPast } from '../utils/validators';
import { useTheme } from '../context/ThemeContext';

const PAGE_SIZE = 9;

export default function Projects() {
  const { locale } = useTheme();
  const { data: projects = [], isLoading } = useProjects();
  const createProject = useCreateProject();
  const { success, error } = useNotifications();
  useWebSocket('projects', ['projects']);

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState({});
  const [showCreate, setShowCreate] = useState(false);

  const { register, handleSubmit, reset, formState: { errors } } = useForm();

  const filtered = useMemo(() => {
    const term = search.toLowerCase();
    return projects.filter((p) => {
      const matchesSearch =
        p.name?.toLowerCase().includes(term) || p.code?.toLowerCase().includes(term);
      const matchesStatus = !status || p.status === status;
      return matchesSearch && matchesStatus;
    });
  }, [projects, search, status]);

  const pageCount = Math.ceil(filtered.length / PAGE_SIZE) || 1;
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const selectedIds = Object.keys(selected).filter((id) => selected[id]);

  const toggleSelect = (id, checked) => setSelected((prev) => ({ ...prev, [id]: checked }));

  const onCreate = async (values) => {
    try {
      await createProject.mutateAsync(values);
      success(locale === 'ar' ? 'تم إنشاء المشروع' : 'Project created');
      setShowCreate(false);
      reset();
    } catch (e) {
      error(e.message);
    }
  };

  const statusOptions = [
    { value: '', label: locale === 'ar' ? 'كل الحالات' : 'All statuses' },
    ...PROJECT_STAGES.map((s) => ({ value: s, label: statusLabel(s, locale) })),
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-brand-green dark:text-brand-gold">
          المشاريع / Projects
        </h1>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          ➕ مشروع جديد / New Project
        </button>
      </div>

      <SearchFilter
        search={search}
        onSearch={(v) => {
          setSearch(v);
          setPage(1);
        }}
        filters={[
          {
            name: 'status',
            label: 'Status',
            value: status,
            onChange: (v) => {
              setStatus(v);
              setPage(1);
            },
            options: statusOptions,
          },
        ]}
      />

      {selectedIds.length > 0 && (
        <div className="mb-3 flex items-center gap-3 rounded-lg bg-brand-gold/15 px-4 py-2 text-sm">
          <span>{selectedIds.length} محدد / selected</span>
          <button className="btn-outline px-3 py-1" onClick={() => setSelected({})}>
            مسح التحديد / Clear
          </button>
        </div>
      )}

      {isLoading ? (
        <Loading />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {pageItems.map((p) => (
              <ProjectCard
                key={p.id}
                project={p}
                selectable
                selected={Boolean(selected[p.id])}
                onSelect={toggleSelect}
              />
            ))}
          </div>
          {filtered.length === 0 && (
            <p className="mt-6 text-gray-500">لا توجد مشاريع / No projects found.</p>
          )}
          <Pagination page={page} pageCount={pageCount} onPage={setPage} />
        </>
      )}

      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title={locale === 'ar' ? 'مشروع جديد' : 'New Project'}
        footer={
          <>
            <button className="btn-outline" onClick={() => setShowCreate(false)}>
              إلغاء / Cancel
            </button>
            <button className="btn-primary" onClick={handleSubmit(onCreate)} disabled={createProject.isPending}>
              إنشاء / Create
            </button>
          </>
        }
      >
        <form className="space-y-3" onSubmit={handleSubmit(onCreate)}>
          <label className="block">
            <span className="text-sm font-medium">اسم المشروع / Project name</span>
            <input className="input mt-1 w-full" {...register('name', { validate: required })} />
            {errors.name && <span className="text-xs text-red-600">{errors.name.message}</span>}
          </label>
          <label className="block">
            <span className="text-sm font-medium">الموقع / Location</span>
            <input className="input mt-1 w-full" {...register('location')} />
          </label>
          <label className="block">
            <span className="text-sm font-medium">تاريخ الافتتاح / Opening date</span>
            <input
              type="date"
              className="input mt-1 w-full"
              {...register('opening_date', { validate: notPast })}
            />
            {errors.opening_date && (
              <span className="text-xs text-red-600">{errors.opening_date.message}</span>
            )}
          </label>
        </form>
      </Modal>
    </div>
  );
}
