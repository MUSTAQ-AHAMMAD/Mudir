// useAnalytics.js — React Query hooks for analytics + AI insights.
import { useQuery } from '@tanstack/react-query';
import * as analyticsApi from '../api/analytics';

export function useAnalytics() {
  return useQuery({ queryKey: ['analytics'], queryFn: analyticsApi.getAnalytics });
}

export function useInsights() {
  return useQuery({ queryKey: ['insights'], queryFn: analyticsApi.getInsights });
}
