import { getTranslations } from 'next-intl/server'
import { TaskForm } from '@/components/task-form'
import { Link } from '@/i18n/navigation'

type TaskSummary = { id: string; goal: string; status: string }

async function getRecentTasks(): Promise<TaskSummary[]> {
  const internalUrl = process.env.AGENTIS_INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
  try {
    const res = await fetch(
      `${internalUrl}/api/v1/tasks?limit=4`,
      { cache: 'no-store' }
    )
    if (!res.ok) return []
    const data = await res.json()
    return (data.items ?? []) as TaskSummary[]
  } catch {
    return []
  }
}

export default async function HomePage() {
  const t = await getTranslations('home')
  const recent = await getRecentTasks()

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-56px)] -mt-8 gap-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-foreground mb-2">{t('title')}</h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>
      <TaskForm />
      {recent.length > 0 && (
        <div className="w-full max-w-2xl">
          <p className="text-sm text-muted-foreground mb-2">{t('recent')}</p>
          <div className="space-y-2">
            {recent.map((task) => (
              <Link key={task.id} href={`/tasks/${task.id}`}>
                <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-card hover:bg-secondary transition-colors cursor-pointer">
                  <span className="text-sm truncate text-foreground">{task.goal}</span>
                  <span className="text-xs text-muted-foreground ml-4 shrink-0">{task.status}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
