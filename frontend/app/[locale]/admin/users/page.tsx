'use client'

import { useEffect, useState } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuthStore } from '@/lib/auth'
import { apiFetch } from '@/lib/api'

interface UserItem {
  id: string
  email: string
  name: string | null
  role: string
  token_used_this_month: number
  created_at: string
}

const roleBadge: Record<string, string> = {
  admin: 'bg-red-500/15 text-red-400 border-red-500/30',
  operator: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  user: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserItem[]>([])
  const [total, setTotal] = useState(0)
  const token = useAuthStore((s) => s.accessToken)

  useEffect(() => {
    if (!token) return
    apiFetch('/api/v1/admin/users?limit=50')
      .then((r) => r.ok ? r.json() : { items: [], total: 0 })
      .then(({ items, total }) => { setUsers(items); setTotal(total) })
      .catch(() => {})
  }, [token])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Utilisateurs</h1>
        <span className="text-sm text-muted-foreground">{total} total</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Nom</TableHead>
            <TableHead>Rôle</TableHead>
            <TableHead className="text-right">Tokens (mois)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.id}>
              <TableCell className="font-mono text-sm">{u.email}</TableCell>
              <TableCell>{u.name ?? '—'}</TableCell>
              <TableCell>
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs border ${roleBadge[u.role] ?? ''}`}>
                  {u.role}
                </span>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {(u.token_used_this_month ?? 0).toLocaleString('fr')}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
