import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface ScheduledTask {
  id: string
  name: string
  goal_template: string
  cron_expression: string
  language: string | null
  allowed_tools: string[] | null
  max_iterations: number | null
  is_active: boolean
  next_run_at: string
  last_run_at: string | null
  last_task_id: string | null
  last_status: string | null
  created_at: string
}

export interface ScheduledTaskCreate {
  name: string
  goal_template: string
  cron_expression: string
  language?: string | null
  max_iterations?: number | null
}

export interface ScheduledTaskUpdate {
  name?: string
  goal_template?: string
  cron_expression?: string
  is_active?: boolean
}

async function parseError(r: Response, fallback: string): Promise<never> {
  const body = await r.json().catch(() => ({}))
  const detail = (body as { error?: { message?: string }; detail?: string })
  throw new Error(detail.error?.message ?? detail.detail ?? fallback)
}

export function useScheduledTasks() {
  return useQuery({
    queryKey: ['scheduled-tasks'],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/scheduled-tasks')
      if (!r.ok) return parseError(r, 'Failed to fetch scheduled tasks')
      return r.json() as Promise<ScheduledTask[]>
    },
  })
}

export function useCreateScheduledTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ScheduledTaskCreate) => {
      const r = await apiFetch('/api/v1/scheduled-tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) return parseError(r, 'Failed to create scheduled task')
      return r.json() as Promise<ScheduledTask>
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-tasks'] }),
  })
}

export function useUpdateScheduledTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...body }: ScheduledTaskUpdate & { id: string }) => {
      const r = await apiFetch(`/api/v1/scheduled-tasks/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) return parseError(r, 'Failed to update scheduled task')
      return r.json() as Promise<ScheduledTask>
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-tasks'] }),
  })
}

export function useDeleteScheduledTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const r = await apiFetch(`/api/v1/scheduled-tasks/${id}`, { method: 'DELETE' })
      if (!r.ok) return parseError(r, 'Failed to delete scheduled task')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-tasks'] }),
  })
}
