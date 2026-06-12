'use client'

import { useEffect, useState } from 'react'
import { Activity, Users, CheckCircle, Clock } from 'lucide-react'
import { KpiCard } from '@/components/admin/KpiCard'
import { TokenUsageBar } from '@/components/admin/TokenUsageBar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuthStore } from '@/lib/auth'
import { apiFetch } from '@/lib/api'

interface AdminStats {
  tasks_today: number
  active_users: number
  tokens_this_month: number
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const token = useAuthStore((s) => s.accessToken)

  useEffect(() => {
    if (!token) return
    apiFetch('/api/v1/admin/stats')
      .then((r) => r.ok ? r.json() : null)
      .then((data) => setStats(data))
      .catch(() => {})
  }, [token])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">Vue d&apos;ensemble de la plateforme</p>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard title="Tâches aujourd'hui" value={stats?.tasks_today ?? '—'} icon={Activity} />
        <KpiCard title="Utilisateurs actifs" value={stats?.active_users ?? '—'} icon={Users} />
        <KpiCard title="Tâches terminées" value="—" icon={CheckCircle} />
        <KpiCard title="Temps moyen" value="—" icon={Clock} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Utilisation tokens</CardTitle>
        </CardHeader>
        <CardContent>
          <TokenUsageBar used={stats?.tokens_this_month ?? 0} limit={10_000_000} />
        </CardContent>
      </Card>
    </div>
  )
}
