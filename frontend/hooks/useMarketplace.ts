import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface MarketplacePlugin {
  id: number
  name: string
  slug: string
  description: string
  source_type: 'mcp' | 'openapi'
  url: string
  version: string
  author: string
  installed: boolean
  registered_tool_name: string | null
}

export function useMarketplacePlugins(installed?: boolean) {
  const params = installed !== undefined ? `?installed=${installed}` : ''
  return useQuery({
    queryKey: ['marketplace', 'plugins', installed],
    queryFn: async () => {
      const r = await apiFetch(`/api/v1/marketplace/plugins${params}`)
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Failed to fetch marketplace plugins')
      }
      return r.json() as Promise<MarketplacePlugin[]>
    },
  })
}

export function useInstallPlugin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (slug: string) => {
      const r = await apiFetch(`/api/v1/marketplace/plugins/${slug}/install`, {
        method: 'POST',
      })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Installation failed')
      }
      return r.json() as Promise<MarketplacePlugin>
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketplace', 'plugins'] })
    },
  })
}
