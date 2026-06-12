import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface TaskSummary {
  id: string
  goal: string
  status: string
  agent_role?: string | null
  parent_task_id?: string | null
}

const ACTIVE_STATUSES = ['submitted', 'planning', 'running', 'waiting_for_input']

export function useSubtasks(taskId: string, parentStatus?: string) {
  return useQuery({
    queryKey: ['tasks', taskId, 'subtasks'],
    queryFn: async () => {
      const r = await apiFetch(`/api/v1/tasks/${taskId}/subtasks`)
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error((body as { detail?: string }).detail ?? 'Failed to fetch subtasks')
      }
      return r.json() as Promise<TaskSummary[]>
    },
    refetchInterval: ACTIVE_STATUSES.includes(parentStatus ?? '') ? 3000 : false,
  })
}
