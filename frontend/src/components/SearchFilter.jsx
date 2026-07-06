// SearchFilter.jsx — search box + a set of dropdown filters.
export default function SearchFilter({
  search = '',
  onSearch,
  filters = [],
  searchPlaceholder = 'بحث… / Search…',
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <input
        className="input w-64"
        type="search"
        placeholder={searchPlaceholder}
        value={search}
        onChange={(e) => onSearch?.(e.target.value)}
        aria-label="Search"
      />
      {filters.map((f) => (
        <label key={f.name} className="flex items-center gap-1 text-sm">
          <span className="sr-only">{f.label}</span>
          <select
            className="input"
            value={f.value}
            onChange={(e) => f.onChange?.(e.target.value)}
            aria-label={f.label}
          >
            {f.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}
