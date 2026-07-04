// StatusBadge.jsx — colour-coded badge for project/task status.
const STYLES = {
  property_pending: 'bg-blue-100 text-blue-800',
  marketing_pending: 'bg-orange-100 text-orange-800',
  it_pending: 'bg-purple-100 text-purple-800',
  ready: 'bg-green-100 text-green-800',
  completed: 'bg-gray-200 text-gray-700',
  overdue: 'bg-red-100 text-red-800',
  done: 'bg-green-100 text-green-800',
  in_progress: 'bg-yellow-100 text-yellow-800',
  pending: 'bg-gray-100 text-gray-600',
  blocked: 'bg-red-100 text-red-800',
};

export default function StatusBadge({ status }) {
  return <span className={`badge ${STYLES[status] || 'bg-gray-100 text-gray-600'}`}>{status}</span>;
}
