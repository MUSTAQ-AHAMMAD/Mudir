// Login.jsx — Supabase Auth sign-in (email/password + Google). Shown when the
// user is not authenticated. In demo mode (no Supabase env) any submit signs in.
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useAuth } from '../hooks/useAuth';
import { isSupabaseConfigured } from '../api/client';
import { required, isEmail, compose } from '../utils/validators';

export default function Login() {
  const { signIn, signInWithGoogle } = useAuth();
  const { register, handleSubmit, formState: { errors } } = useForm();
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (values) => {
    setBusy(true);
    setError(null);
    try {
      await signIn(values);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-green bg-saudi-pattern p-4">
      <div className="card w-full max-w-sm bg-white p-6 dark:bg-brand-greenDark">
        <div className="mb-6 text-center">
          <div className="text-3xl" aria-hidden="true">🌙</div>
          <h1 className="text-2xl font-bold text-brand-gold">مدير · Mudir</h1>
          <p className="text-sm text-gray-500 dark:text-gray-300">لوحة تحكم المشرف / Admin Dashboard</p>
        </div>

        {!isSupabaseConfigured && (
          <p className="mb-4 rounded-lg bg-brand-gold/15 p-2 text-center text-xs text-brand-greenDark dark:text-brand-gold">
            وضع تجريبي — أي بيانات تسجّل الدخول / Demo mode — any credentials sign you in.
          </p>
        )}

        <form className="space-y-3" onSubmit={handleSubmit(onSubmit)}>
          <label className="block">
            <span className="text-sm font-medium">البريد الإلكتروني / Email</span>
            <input
              type="email"
              className="input mt-1 w-full"
              {...register('email', { validate: compose(required, isEmail) })}
            />
            {errors.email && <span className="text-xs text-red-600">{errors.email.message}</span>}
          </label>
          <label className="block">
            <span className="text-sm font-medium">كلمة المرور / Password</span>
            <input type="password" className="input mt-1 w-full" {...register('password', { validate: required })} />
            {errors.password && <span className="text-xs text-red-600">{errors.password.message}</span>}
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button className="btn-primary w-full" type="submit" disabled={busy}>
            دخول / Sign in
          </button>
        </form>

        {isSupabaseConfigured && (
          <button className="btn-outline mt-3 w-full" onClick={() => signInWithGoogle().catch((e) => setError(e.message))}>
            الدخول عبر Google / Continue with Google
          </button>
        )}
      </div>
    </div>
  );
}
