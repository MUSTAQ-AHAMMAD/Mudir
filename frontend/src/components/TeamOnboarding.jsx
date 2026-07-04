// TeamOnboarding.jsx — setup wizard for a new company.
// Step 1: company details. Step 2: add team leads. Step 3: define workflow order.
// On finish it upserts each team lead via the API.
import { useState } from 'react';
import { api } from '../lib/api';

const emptyLead = { name: '', team_name: '', whatsapp_number: '', escalation_number: '' };

export default function TeamOnboarding() {
  const [step, setStep] = useState(1);
  const [company, setCompany] = useState({ name: '', industry: 'retail', teamCount: 3 });
  const [leads, setLeads] = useState([{ ...emptyLead }]);
  const [workflow, setWorkflow] = useState('property, marketing, it');
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const updateLead = (i, key, value) =>
    setLeads((prev) => prev.map((l, idx) => (idx === i ? { ...l, [key]: value } : l)));

  const addLead = () => setLeads((prev) => [...prev, { ...emptyLead }]);
  const removeLead = (i) => setLeads((prev) => prev.filter((_, idx) => idx !== i));

  const finish = async () => {
    setError(null);
    try {
      // Persist each team lead. Company + workflow would be stored via a
      // dedicated endpoint in a full build; team leads are the critical data.
      await Promise.all(
        leads
          .filter((l) => l.team_name && l.whatsapp_number)
          .map((l) =>
            api.upsertTeamLead({
              team_name: l.team_name.toLowerCase().trim(),
              whatsapp_number: l.whatsapp_number.trim(),
              escalation_number: l.escalation_number.trim() || null,
            }),
          ),
      );
      setSaved(true);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-brand-green mb-1">الإعداد / Onboarding</h1>
      <p className="text-sm text-gray-500 mb-6">Set up your company, teams and workflow.</p>

      <div className="flex gap-2 mb-6">
        {[1, 2, 3].map((s) => (
          <div
            key={s}
            className={`h-2 flex-1 rounded-full ${s <= step ? 'bg-brand-gold' : 'bg-gray-200'}`}
          />
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium">Company name</span>
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={company.name}
              onChange={(e) => setCompany({ ...company, name: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium">Industry</span>
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={company.industry}
              onChange={(e) => setCompany({ ...company, industry: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium">Number of teams</span>
            <input
              type="number"
              min="1"
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={company.teamCount}
              onChange={(e) => setCompany({ ...company, teamCount: Number(e.target.value) })}
            />
          </label>
          <button className="px-4 py-2 rounded-lg bg-brand-green text-white" onClick={() => setStep(2)}>
            Next →
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          {leads.map((lead, i) => (
            <div key={i} className="rounded-lg border p-3 grid gap-2 sm:grid-cols-2">
              <input
                className="border rounded px-2 py-1"
                placeholder="Lead name"
                value={lead.name}
                onChange={(e) => updateLead(i, 'name', e.target.value)}
              />
              <input
                className="border rounded px-2 py-1"
                placeholder="Team (e.g. marketing)"
                value={lead.team_name}
                onChange={(e) => updateLead(i, 'team_name', e.target.value)}
              />
              <input
                className="border rounded px-2 py-1"
                placeholder="WhatsApp (+9665…)"
                value={lead.whatsapp_number}
                onChange={(e) => updateLead(i, 'whatsapp_number', e.target.value)}
              />
              <input
                className="border rounded px-2 py-1"
                placeholder="Escalation (+9665…)"
                value={lead.escalation_number}
                onChange={(e) => updateLead(i, 'escalation_number', e.target.value)}
              />
              {leads.length > 1 && (
                <button className="text-sm text-red-600 text-left" onClick={() => removeLead(i)}>
                  Remove
                </button>
              )}
            </div>
          ))}
          <button className="text-sm text-brand-greenLight" onClick={addLead}>
            + Add team lead
          </button>
          <div className="flex gap-2">
            <button className="px-4 py-2 rounded-lg border" onClick={() => setStep(1)}>
              ← Back
            </button>
            <button className="px-4 py-2 rounded-lg bg-brand-green text-white" onClick={() => setStep(3)}>
              Next →
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium">Workflow order (comma-separated)</span>
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={workflow}
              onChange={(e) => setWorkflow(e.target.value)}
            />
            <span className="text-xs text-gray-400">e.g. property, marketing, it, logistics</span>
          </label>
          <div className="flex gap-2">
            <button className="px-4 py-2 rounded-lg border" onClick={() => setStep(2)}>
              ← Back
            </button>
            <button className="px-4 py-2 rounded-lg bg-brand-gold text-brand-green font-semibold" onClick={finish}>
              Finish setup
            </button>
          </div>
          {saved && <p className="text-green-600">✅ Team leads saved.</p>}
          {error && <p className="text-red-600">Error: {error}</p>}
        </div>
      )}
    </div>
  );
}
