'use client'

import { useEffect, useState } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuthStore } from '@/lib/auth'
import { apiFetch } from '@/lib/api'

interface AuditItem {
  id: string
  actor_email: string
  action: string
  resource_type: string
  resource_id: string | null
  created_at: string
}

export default function AdminAuditPage() {
  const [events, setEvents] = useState<AuditItem[]>([])
  const token = useAuthStore((s) => s.accessToken)

  useEffect(() => {
    if (!token) return
    apiFetch('/api/v1/admin/audit?limit=50')
      .then((r) => r.ok ? r.json() : { items: [] })
      .then(({ items }) => setEvents(items))
      .catch(() => {})
  }, [token])

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Audit Log</h1>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Date</TableHead>
            <TableHead>Acteur</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Ressource</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                Aucun événement
              </TableCell>
            </TableRow>
          )}
          {events.map((e) => (
            <TableRow key={e.id}>
              <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                {new Date(e.created_at).toLocaleString('fr')}
              </TableCell>
              <TableCell className="font-mono text-xs">{e.actor_email}</TableCell>
              <TableCell>
                <code className="bg-muted px-1.5 py-0.5 rounded text-xs">{e.action}</code>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {e.resource_type}{e.resource_id ? ` / ${e.resource_id.slice(0, 8)}…` : ''}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
