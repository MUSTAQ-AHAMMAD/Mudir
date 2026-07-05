// TeamMember.jsx — avatar + name chip for a team member / lead.
import { initials } from '../utils/formatting';
import { avatarColor } from '../utils/colors';

export default function TeamMember({ name, role, size = 'md' }) {
  const sizes = { sm: 'h-7 w-7 text-xs', md: 'h-9 w-9 text-sm', lg: 'h-12 w-12 text-base' };
  const display = name || 'Unknown';
  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-flex items-center justify-center rounded-full font-semibold text-white ${sizes[size] || sizes.md}`}
        style={{ backgroundColor: avatarColor(display) }}
        aria-hidden="true"
      >
        {initials(display)}
      </span>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{display}</div>
        {role && <div className="truncate text-xs capitalize text-gray-400">{role}</div>}
      </div>
    </div>
  );
}
