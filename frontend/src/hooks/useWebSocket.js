// useWebSocket.js — real-time updates via Supabase Postgres change subscriptions.
//
// Subscribes to changes on a table and invalidates the matching React Query
// cache key so the UI updates live. No-op when Supabase is not configured.
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { supabase, isSupabaseConfigured } from '../api/client';

/**
 * @param {string} table  Postgres table to watch (e.g. 'projects').
 * @param {(string|any[])} invalidateKey React Query key to invalidate on change.
 * @param {(payload:any)=>void} [onChange] optional custom handler.
 */
export function useWebSocket(table, invalidateKey, onChange) {
  const qc = useQueryClient();

  useEffect(() => {
    if (!isSupabaseConfigured || !table) return undefined;

    const channel = supabase
      .channel(`realtime:${table}`)
      .on('postgres_changes', { event: '*', schema: 'public', table }, (payload) => {
        if (onChange) onChange(payload);
        if (invalidateKey) {
          qc.invalidateQueries({ queryKey: Array.isArray(invalidateKey) ? invalidateKey : [invalidateKey] });
        }
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table, JSON.stringify(invalidateKey)]);
}

export default useWebSocket;
