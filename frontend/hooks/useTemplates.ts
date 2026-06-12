import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface TaskTemplate {
  id: number
  name: string
  description: string | null
  goal_template: string
  category: string | null
  created_at: string
  is_public: boolean
}

export function useTemplates() {
  return useQuery({
    queryKey: ['templates'],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/templates')
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Failed to fetch templates')
      }
      return r.json() as Promise<TaskTemplate[]>
    },
  })
}
