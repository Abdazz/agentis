import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface LlmConfig {
  provider: string
  model: string
  api_key_masked: string
  base_url: string
}

export interface LlmConfigPatch {
  provider?: string
  model?: string
  api_key?: string
  base_url?: string
}

export function useAdminConfig(role: string | null) {
  return useQuery({
    queryKey: ['admin', 'config', 'llm'],
    enabled: role === 'operator',
    queryFn: async () => {
      const r = await apiFetch('/api/v1/admin/config/llm')
      if (!r.ok) throw new Error('Failed to fetch LLM config')
      return r.json() as Promise<LlmConfig>
    },
  })
}

export function useUpdateAdminConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (patch: LlmConfigPatch) => {
      const r = await apiFetch('/api/v1/admin/config/llm', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!r.ok) {
        const body = await r.json().catch(() => null)
        const msg = typeof body?.detail === 'string' ? body.detail : 'Failed to update config'
        throw new Error(msg)
      }
      return r.json() as Promise<LlmConfig>
    },
    onSuccess: (data) => {
      qc.setQueryData(['admin', 'config', 'llm'], data)
    },
  })
}
