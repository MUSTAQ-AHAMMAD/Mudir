// export.js — client-side CSV and PDF export helpers with no extra dependencies.
// CSV is generated in-browser and downloaded; PDF uses the browser's native
// print-to-PDF (window.print) scoped via a print stylesheet / print:hidden.

/** Trigger a browser download of `content` as `filename`. */
function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Escape a single CSV cell. */
function csvCell(value) {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (/[",\n]/.test(str)) return `"${str.replace(/"/g, '""')}"`;
  return str;
}

/**
 * Export an array of row objects to CSV.
 * @param {Object[]} rows
 * @param {string} filename
 * @param {string[]} [columns] explicit column order; defaults to keys of first row.
 */
export function exportCSV(rows, filename = 'export.csv', columns) {
  const list = Array.isArray(rows) ? rows : [];
  const cols = columns || (list[0] ? Object.keys(list[0]) : []);
  const header = cols.map(csvCell).join(',');
  const body = list.map((row) => cols.map((c) => csvCell(row[c])).join(',')).join('\n');
  // Prepend BOM so Excel opens UTF-8 (Arabic) correctly.
  downloadBlob(`\uFEFF${header}\n${body}`, filename, 'text/csv;charset=utf-8;');
}

/**
 * Export via the browser's print dialog (user can "Save as PDF").
 * Optionally pass a title used as the document title during printing.
 */
export function exportPDF(title) {
  const previous = document.title;
  if (title) document.title = title;
  window.print();
  // Restore the title shortly after the print dialog opens.
  setTimeout(() => {
    document.title = previous;
  }, 500);
}

/** Export a JSON object as a downloadable .json file (workflow import/export). */
export function exportJSON(data, filename = 'export.json') {
  downloadBlob(JSON.stringify(data, null, 2), filename, 'application/json');
}

/** Read a user-selected File as parsed JSON (workflow import). Returns a Promise. */
export function importJSONFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        resolve(JSON.parse(String(reader.result)));
      } catch (e) {
        reject(new Error('Invalid JSON file'));
      }
    };
    reader.onerror = () => reject(new Error('Could not read file'));
    reader.readAsText(file);
  });
}
