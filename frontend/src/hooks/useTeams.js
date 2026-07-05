// useTeams.js — React Query hooks for teams / team leads.
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as teamsApi from '../api/teams';

export function useTeams() {
  return useQuery({ queryKey: ['teams'], queryFn: teamsApi.listTeams });
}

export function useUpsertTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: teamsApi.upsertTeam,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams'] }),
  });
}

export function useDeleteTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: teamsApi.deleteTeam,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams'] }),
  });
}
