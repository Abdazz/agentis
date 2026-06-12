import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface OrgItem {
  id: string
  name: string
  slug: string
  member_count: number
  token_budget_monthly: number | null
  created_at: string
}

export interface OrgListResponse {
  items: OrgItem[]
  total: number
}

export function useAdminOrgs() {
  return useQuery({
    queryKey: ['admin', 'orgs'],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/admin/organizations')
      if (!r.ok) throw new Error('Failed to fetch organizations')
      return r.json() as Promise<OrgListResponse>
    },
  })
}

export function useCreateOrg() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { name: string; slug: string }) => {
      const r = await apiFetch('/api/v1/organizations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? 'Failed to create organization')
      }
      return r.json()
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'orgs'] }),
  })
}

export function useDeleteOrg() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const r = await apiFetch(`/api/v1/admin/organizations/${id}`, { method: 'DELETE' })
      if (!r.ok) throw new Error('Failed to delete organization')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'orgs'] }),
  })
}
