'use client'

import { useInfiniteQuery } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { Link } from '@/i18n/navigation'
import { apiFetch } from '@/lib/api'

type Task = {
  id: string
  goal: string
  status: string
  created_at: string
  duration_ms: number | null
}

type TaskPage = {
  items: Task[]
  next_cursor: string | null
}

async function fetchTasks(cursor?: string): Promise<TaskPage> {
  const params = new URLSearchParams({ limit: '20' })
  if (cursor) params.set('cursor', cursor)
  const res = await apiFetch(`/api/v1/tasks?${params}`)
  if (!res.ok) throw new Error('Failed to fetch tasks')
  return res.json()
}

const STATUS_COLORS: Record<string, string> = {
  running: 'text-primary',
  completed: 'text-success',
  failed: 'text-destructive',
  cancelled: 'text-muted-foreground',
  pending: 'text-muted-foreground',
  waiting_for_input: 'text-primary',
}

function formatDuration(ms: number | null): string {
  if (!ms) return '—'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export function TaskList({ initialItems }: { initialItems: Task[] }) {
  const t = useTranslations('tasks')

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['tasks'],
    queryFn: ({ pageParam }) => fetchTasks(pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    initialData: {
      pages: [{ items: initialItems, next_cursor: null }],
      pageParams: [undefined],
    },
  })

  const tasks = data.pages.flatMap((p) => p.items)

  if (tasks.length === 0) {
    return <p className="text-muted-foreground">{t('empty')}</p>
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <Link key={task.id} href={`/tasks/${task.id}`}>
          <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-card hover:bg-secondary transition-colors cursor-pointer">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground truncate">{task.goal}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {new Date(task.created_at).toLocaleString()}
              </p>
            </div>
            <div className="ml-4 flex items-center gap-4 shrink-0">
              <span className="text-xs text-muted-foreground">{formatDuration(task.duration_ms)}</span>
              <span className={`text-xs font-medium ${STATUS_COLORS[task.status] ?? 'text-muted-foreground'}`}>
                {t(`status.${task.status}` as Parameters<typeof t>[0])}
              </span>
            </div>
          </div>
        </Link>
      ))}
      {hasNextPage && (
        <button
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
          className="w-full py-2 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50"
        >
          {isFetchingNextPage ? '…' : 'Load more'}
        </button>
      )}
    </div>
  )
}
