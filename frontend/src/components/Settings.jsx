// Settings.jsx — edit team leads' phone numbers, escalation rules and the
// Saudi working week. Team-lead changes are persisted via the API; escalation
// threshold and working days are surfaced here (server-configured via env).
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

export default function Settings() {
  const [leads, setLeads] = useState([]);
  const [escalateDays, setEscalateDays] = useState(2);
  const [workingDays, setWorkingDays] = useState({
    Sun: true,
    Mon: true,
    Tue: true,
    Wed: true,
    Thu: true,
    Fri: false,
    Sat: false,
  });
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.listTeamLeads().then((d) => setLeads(d.teamLeads || [])).catch((e) => setError(e.message));
  }, []);

  const updateLead = (i, key, value) =>
    setLeads((prev) => prev.map((l, idx) => (idx === i ? { ...l, [key]: value } : l)));

  const saveLead = async (lead) => {
    setStatus(null);
    try {
      await api.upsertTeamLead({
        team_name: lead.team_name,
        whatsapp_number: lead.whatsapp_number,
        escalation_number: lead.escalation_number || null,
      });
      setStatus(`Saved ${lead.team_name}.`);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-brand-green mb-4">الإعدادات / Settings</h1>

      <section className="mb-8">
        <h2 className="font-semibold mb-3">Team leads</h2>
        <div className="space-y-3">
          {leads.map((lead, i) => (
            <div key={lead.id || i} className="rounded-lg border p-3 grid gap-2 sm:grid-cols-2">
              <div className="text-sm font-medium capitalize self-center">{lead.team_name}</div>
              <input
                className="border rounded px-2 py-1"
                value={lead.whatsapp_number}
                onChange={(e) => updateLead(i, 'whatsapp_number', e.target.value)}
              />
              <input
                className="border rounded px-2 py-1"
                placeholder="Escalation number"
                value={lead.escalation_number || ''}
                onChange={(e) => updateLead(i, 'escalation_number', e.target.value)}
              />
              <button
                className="text-sm px-3 py-1 rounded bg-brand-green text-white justify-self-start"
                onClick={() => saveLead(lead)}
              >
                Save
              </button>
            </div>
          ))}
          {leads.length === 0 && <p className="text-sm text-gray-400">No team leads yet.</p>}
        </div>
      </section>

      <section className="mb-8">
        <h2 className="font-semibold mb-3">Escalation rule</h2>
        <label className="flex items-center gap-2 text-sm">
          Escalate if a task is overdue by
          <input
            type="number"
            min="1"
            className="border rounded px-2 py-1 w-16"
            value={escalateDays}
            onChange={(e) => setEscalateDays(Number(e.target.value))}
          />
          day(s).
        </label>
        <p className="text-xs text-gray-400 mt-1">
          Configured server-side via <code>ESCALATE_AFTER_DAYS</code>.
        </p>
      </section>

      <section>
        <h2 className="font-semibold mb-3">Working days (Saudi)</h2>
        <div className="flex flex-wrap gap-2">
          {Object.keys(workingDays).map((day) => (
            <label
              key={day}
              className={`px-3 py-1 rounded-full border cursor-pointer text-sm ${
                workingDays[day] ? 'bg-brand-green text-white' : 'bg-white'
              }`}
            >
              <input
                type="checkbox"
                className="hidden"
                checked={workingDays[day]}
                onChange={() => setWorkingDays({ ...workingDays, [day]: !workingDays[day] })}
              />
              {day}
            </label>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-1">
          Configured server-side via <code>WEEKEND_DAYS</code> (default Fri, Sat off).
        </p>
      </section>

      {status && <p className="text-green-600 mt-4">{status}</p>}
      {error && <p className="text-red-600 mt-4">Error: {error}</p>}
    </div>
  );
}
