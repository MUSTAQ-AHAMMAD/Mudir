// useWorkflows.js — React Query hooks for workflows + AI suggestions.
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as workflowsApi from '../api/workflows';

export function useWorkflows() {
  return useQuery({ queryKey: ['workflows'], queryFn: workflowsApi.listWorkflows });
}

export function useWorkflowSuggestions() {
  return useQuery({
    queryKey: ['workflow-suggestions'],
    queryFn: workflowsApi.listWorkflowSuggestions,
  });
}

export function useSaveWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: workflowsApi.saveWorkflow,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workflows'] }),
  });
}

export function useResolveSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, accepted }) => workflowsApi.resolveSuggestion(id, accepted),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workflow-suggestions'] });
      qc.invalidateQueries({ queryKey: ['workflows'] });
    },
  });
}
