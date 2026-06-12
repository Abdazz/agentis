import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface ToolConfig {
  name: string
  enabled_globally: boolean
  allowed_orgs: string[] | null
  source: 'builtin' | 'mcp' | 'openapi'
  mcp_url: string | null
  openapi_spec_url: string | null
}

export function useAdminTools() {
  return useQuery({
    queryKey: ['admin', 'tools'],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/admin/tools')
      if (!r.ok) throw new Error('Failed to fetch tools')
      return r.json() as Promise<ToolConfig[]>
    },
  })
}

export function useToggleTool() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, enabled }: { name: string; enabled: boolean }) => {
      const r = await apiFetch(`/api/v1/admin/tools/${name}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled_globally: enabled }),
      })
      if (!r.ok) throw new Error('Failed to update tool')
      return r.json() as Promise<ToolConfig>
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tools'] }),
  })
}
