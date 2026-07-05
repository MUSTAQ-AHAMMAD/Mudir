// useProjects.js — React Query hooks for project data + mutations.
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as projectsApi from '../api/projects';

export function useProjects(filters = {}) {
  return useQuery({
    queryKey: ['projects', filters],
    queryFn: () => projectsApi.listProjects(filters),
  });
}

export function useProject(code) {
  return useQuery({
    queryKey: ['project', code],
    queryFn: () => projectsApi.getProject(code),
    enabled: Boolean(code),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: projectsApi.createProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }) => projectsApi.updateProject(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  });
}

export function useAddTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, task }) => projectsApi.addTask(projectId, task),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['project'] }),
  });
}
