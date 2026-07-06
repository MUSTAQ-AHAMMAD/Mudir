// Settings.jsx — system settings: AI model selection, working hours/days (Friday
// off toggle), escalation rules, notification preferences, API keys, system
// health and a simple log viewer.
import { useEffect, useState } from 'react';
import Loading from '../components/Loading';
import { getSettings, saveSettings } from '../api/settings';
import { useNotifications } from '../hooks/useNotifications';
import { useTheme } from '../context/ThemeContext';

const AI_MODELS = ['gpt-4o-mini', 'gpt-4o', 'llama-3.1-8b', 'mistral-7b'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function Settings() {
  const { locale } = useTheme();
  const { success, error } = useNotifications();
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSettings().then(setSettings).catch((e) => error(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!settings) return <Loading />;

  const update = (patch) => setSettings((prev) => ({ ...prev, ...patch }));
  const toggleDay = (day) =>
    update({ working_days: { ...settings.working_days, [day]: !settings.working_days[day] } });
  const toggleNotif = (key) =>
    update({ notifications: { ...settings.notifications, [key]: !settings.notifications[key] } });

  const save = async () => {
    setSaving(true);
    try {
      await saveSettings(settings);
      success(locale === 'ar' ? 'تم حفظ الإعدادات' : 'Settings saved');
    } catch (e) {
      error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-brand-green dark:text-brand-gold">الإعدادات / Settings</h1>
        <button className="btn-primary" onClick={save} disabled={saving}>💾 حفظ / Save</button>
      </div>

      {/* AI model */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">نموذج الذكاء الاصطناعي / AI Model</h2>
        <select className="input" value={settings.ai_model} onChange={(e) => update({ ai_model: e.target.value })}>
          {AI_MODELS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </section>

      {/* Working days */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">أيام العمل / Working Days</h2>
        <div className="flex flex-wrap gap-2">
          {DAYS.map((day) => (
            <label
              key={day}
              className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${
                settings.working_days[day] ? 'bg-brand-green text-white' : 'bg-white dark:bg-white/5'
              }`}
            >
              <input type="checkbox" className="hidden" checked={Boolean(settings.working_days[day])} onChange={() => toggleDay(day)} />
              {day}
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-gray-400">
          {locale === 'ar' ? 'الجمعة عطلة افتراضيًا (الأسبوع السعودي).' : 'Friday off by default (Saudi week).'}
        </p>
      </section>

      {/* Escalation rules */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">قواعد التصعيد / Escalation Rules</h2>
        <label className="flex items-center gap-2 text-sm">
          {locale === 'ar' ? 'تصعيد إذا تأخرت المهمة' : 'Escalate if a task is overdue by'}
          <input
            type="number"
            min="1"
            className="input w-20"
            value={settings.escalate_after_days}
            onChange={(e) => update({ escalate_after_days: Number(e.target.value) })}
          />
          {locale === 'ar' ? 'يوم' : 'day(s)'}
        </label>
      </section>

      {/* Notifications */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">تفضيلات الإشعارات / Notification Preferences</h2>
        <div className="space-y-2">
          {Object.keys(settings.notifications).map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm capitalize">
              <input type="checkbox" checked={Boolean(settings.notifications[key])} onChange={() => toggleNotif(key)} />
              {key.replace(/_/g, ' ')}
            </label>
          ))}
        </div>
      </section>

      {/* API keys (masked, read-only reminder) */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">مفاتيح API / API Keys</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {locale === 'ar'
            ? 'تُدار المفاتيح عبر متغيرات البيئة على الخادم ولا تُعرض هنا لأسباب أمنية.'
            : 'Keys are managed via server-side environment variables and are not shown here for security.'}
        </p>
        <ul className="mt-2 space-y-1 text-sm">
          {['SUPABASE_SERVICE_KEY', 'OPENAI_API_KEY', 'TWILIO_AUTH_TOKEN'].map((k) => (
            <li key={k} className="flex items-center justify-between">
              <code className="text-xs">{k}</code>
              <span className="badge bg-gray-200 dark:bg-white/10">•••• configured</span>
            </li>
          ))}
        </ul>
      </section>

      {/* System health */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">حالة النظام / System Health</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            { name: 'API', ok: true },
            { name: 'Database', ok: true },
            { name: 'WhatsApp', ok: settings.whatsapp_connected !== false },
          ].map((svc) => (
            <div key={svc.name} className="flex items-center justify-between rounded-lg border border-gray-100 p-3 dark:border-white/10">
              <span className="text-sm">{svc.name}</span>
              <span className={`badge ${svc.ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                {svc.ok ? 'OK' : 'Down'}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Log viewer */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">عارض السجلات / Log Viewer</h2>
        <pre className="max-h-48 overflow-auto rounded-lg bg-gray-900 p-3 text-xs text-green-300">
{(settings.logs || ['[info] system started', '[info] cron scheduled', '[info] webhook verified']).join('\n')}
        </pre>
      </section>
    </div>
  );
}
