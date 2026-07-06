// WhatsAppSettings.jsx — WhatsApp integration settings: WATI/provider connection
// status, group management, template editor, webhook status and a test message
// sender.
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import StatusBadge from '../components/StatusBadge';
import Loading from '../components/Loading';
import { getWhatsAppStatus, sendTestMessage } from '../api/settings';
import { useNotifications } from '../hooks/useNotifications';
import { required, isPhone, compose } from '../utils/validators';
import { useTheme } from '../context/ThemeContext';

const DEFAULT_TEMPLATE = 'مرحبًا {{name}}، مشروع {{project}} بحاجة إلى تحديث.\nHi {{name}}, project {{project}} needs an update.';

export default function WhatsAppSettings() {
  const { locale } = useTheme();
  const { success, error } = useNotifications();
  const [status, setStatus] = useState(null);
  const [template, setTemplate] = useState(DEFAULT_TEMPLATE);
  const [sending, setSending] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm();

  useEffect(() => {
    getWhatsAppStatus().then(setStatus).catch((e) => error(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!status) return <Loading />;

  const onTest = async (values) => {
    setSending(true);
    try {
      await sendTestMessage(values);
      success(locale === 'ar' ? 'تم إرسال رسالة الاختبار' : 'Test message sent');
    } catch (e) {
      error(e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-8">
      <h1 className="text-2xl font-bold text-brand-green dark:text-brand-gold">
        إعدادات واتساب / WhatsApp Settings
      </h1>

      {/* Connection status */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">حالة الاتصال / Connection Status</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="flex items-center justify-between rounded-lg border border-gray-100 p-3 dark:border-white/10">
            <span className="text-sm">WATI / Provider</span>
            <StatusBadge status={status.connected ? 'ready' : 'blocked'} label={status.connected ? 'Connected' : 'Disconnected'} />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-gray-100 p-3 dark:border-white/10">
            <span className="text-sm">Webhook</span>
            <StatusBadge
              status={status.webhook === 'ok' ? 'ready' : 'pending'}
              label={status.webhook === 'ok' ? 'Verified' : status.webhook || 'Unknown'}
            />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-gray-100 p-3 dark:border-white/10">
            <span className="text-sm">Provider</span>
            <span className="text-sm font-medium">{status.provider || '—'}</span>
          </div>
        </div>
      </section>

      {/* Group management */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">إدارة المجموعات / Group Management</h2>
        <ul className="space-y-2">
          {(status.groups || []).map((g) => (
            <li key={g.id || g.name} className="flex items-center justify-between rounded-lg border border-gray-100 p-2 dark:border-white/10">
              <span className="text-sm">{g.name || g.id}</span>
              <span className="text-xs text-gray-400">{g.members ?? '—'} {locale === 'ar' ? 'عضو' : 'members'}</span>
            </li>
          ))}
          {(status.groups || []).length === 0 && (
            <li className="text-sm text-gray-400">لا توجد مجموعات / No groups configured.</li>
          )}
        </ul>
      </section>

      {/* Template editor */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">محرر القوالب / Template Editor</h2>
        <textarea
          className="input w-full font-mono"
          rows={4}
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        />
        <p className="mt-1 text-xs text-gray-400">
          {locale === 'ar' ? 'استخدم {{name}} و {{project}} كمتغيرات.' : 'Use {{name}} and {{project}} as variables.'}
        </p>
      </section>

      {/* Test message sender */}
      <section className="card p-4">
        <h2 className="mb-3 font-semibold">إرسال رسالة اختبار / Send Test Message</h2>
        <form className="space-y-3" onSubmit={handleSubmit(onTest)}>
          <label className="block">
            <span className="text-sm font-medium">إلى / To (WhatsApp number)</span>
            <input
              className="input mt-1 w-full"
              placeholder="+9665XXXXXXXX"
              {...register('to', { validate: compose(required, isPhone) })}
            />
            {errors.to && <span className="text-xs text-red-600">{errors.to.message}</span>}
          </label>
          <label className="block">
            <span className="text-sm font-medium">الرسالة / Message</span>
            <textarea className="input mt-1 w-full" rows={3} defaultValue={template} {...register('message', { validate: required })} />
            {errors.message && <span className="text-xs text-red-600">{errors.message.message}</span>}
          </label>
          <button className="btn-primary" type="submit" disabled={sending}>
            📤 إرسال / Send
          </button>
        </form>
      </section>
    </div>
  );
}
