import { Suspense } from 'react'
import { getTranslations } from 'next-intl/server'
import { TaskList } from '@/components/task-list'
import { OidcTokenPickup } from '@/components/oidc-token-pickup'

type Task = { id: string; goal: string; status: string; created_at: string; duration_ms: number | null }

async function getFirstPage(): Promise<Task[]> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/v1/tasks?limit=20`,
      { cache: 'no-store' }
    )
    if (!res.ok) return []
    const data = await res.json()
    return (data.items ?? []) as Task[]
  } catch {
    return []
  }
}

export default async function TasksPage() {
  const t = await getTranslations('tasks')
  const initial = await getFirstPage()

  return (
    <div>
      {/* Pick up ?token= from OIDC callback and store it — no-op when absent */}
      <Suspense fallback={null}>
        <OidcTokenPickup />
      </Suspense>
      <h1 className="text-2xl font-bold mb-6">{t('title')}</h1>
      <TaskList initialItems={initial} />
    </div>
  )
}
