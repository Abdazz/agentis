'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { connectSSE, type SSEEvent } from '@/lib/sse'
import { apiFetch } from '@/lib/api'
import { Button } from './ui/button'

type EventLine = {
  id: string
  type: string
  content: string
  badge: string
  badgeClass: string
}

const EVENT_CONFIG: Record<string, { badge: string; badgeClass: string }> = {
  plan_created:       { badge: 'events.plan',    badgeClass: 'bg-blue-100 text-blue-700' },
  plan_updated:       { badge: 'events.plan',    badgeClass: 'bg-blue-100 text-blue-700' },
  think:              { badge: 'events.think',   badgeClass: 'bg-purple-100 text-purple-700' },
  tool_call:          { badge: 'events.tool',    badgeClass: 'bg-amber-100 text-amber-700' },
  tool_result:        { badge: 'events.result',  badgeClass: 'bg-green-100 text-green-700' },
  context_summarized: { badge: 'events.summary', badgeClass: 'bg-slate-100 text-slate-600' },
  task_completed:     { badge: 'events.done',    badgeClass: 'bg-green-100 text-green-700' },
  task_failed:        { badge: 'events.error',   badgeClass: 'bg-red-100 text-red-700' },
  task_cancelled:     { badge: 'events.error',   badgeClass: 'bg-red-100 text-red-700' },
}

function extractContent(type: string, data: unknown): string {
  if (!data || typeof data !== 'object') return String(data ?? '')
  const d = data as Record<string, unknown>
  if (type === 'think') return String(d.content ?? '')
  if (type === 'tool_call') return `${d.tool as string}(${JSON.stringify(d.params)})`
  if (type === 'tool_result') return `${d.tool as string} → ${d.duration_ms as number}ms`
  if (type === 'plan_created' || type === 'plan_updated') {
    const tasks = (d.tasks as Array<{ title: string }> | undefined) ?? []
    return `${tasks.length} sub-task(s): ${tasks.map((t) => t.title).join(', ')}`
  }
  if (type === 'task_completed') return String(d.summary ?? 'Task completed')
  if (type === 'task_failed') return String(d.error ?? 'Task failed')
  if (type === 'context_summarized') return `${d.tokens_freed as number} tokens freed`
  return JSON.stringify(data)
}

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

export function TaskFeed({
  taskId,
  status: initialStatus,
  goal,
}: {
  taskId: string
  status: string
  goal: string
}) {
  const t = useTranslations()
  const [lines, setLines] = useState<EventLine[]>([])
  const [status, setStatus] = useState(initialStatus)
  const [confidence, setConfidence] = useState<number | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const userScrolled = useRef(false)
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!userScrolled.current && bottomRef.current?.scrollIntoView) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines])

  useEffect(() => {
    function handleScroll() {
      const el = feedRef.current
      if (!el) return
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
      userScrolled.current = !atBottom
    }
    feedRef.current?.addEventListener('scroll', handleScroll)
    return () => feedRef.current?.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    const url = `/api/v1/tasks/${taskId}/stream`

    const disconnect = connectSSE(url, {
      onEvent: (event: SSEEvent) => {
        const cfg = EVENT_CONFIG[event.type]
        if (!cfg) return
        const content = extractContent(event.type, event.data)
        setLines((prev) => [
          ...prev,
          { id: event.id, type: event.type, content, badge: cfg.badge, badgeClass: cfg.badgeClass },
        ])
        if (event.type === 'plan_updated' || event.type === 'plan_created') {
          const d = event.data as Record<string, unknown>
          if (typeof d.confidence === 'number') setConfidence(d.confidence)
        }
        if (event.type === 'task_completed') setStatus('completed')
        if (event.type === 'task_failed') setStatus('failed')
      },
    })
    return disconnect
  }, [taskId, initialStatus])

  async function handleCancel() {
    setIsCancelling(true)
    await apiFetch(`/api/v1/tasks/${taskId}`, { method: 'DELETE' })
    setStatus('cancelled')
    setIsCancelling(false)
  }

  const isActive = !TERMINAL_STATUSES.has(status)

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="font-medium text-foreground truncate max-w-xl">{goal}</p>
          <p className={`text-sm mt-0.5 ${isActive ? 'text-primary' : 'text-muted-foreground'}`}>
            {isActive ? '● ' : ''}{t(`tasks.status.${status}` as Parameters<typeof t>[0])}
          </p>
        </div>
        {isActive && (
          <Button
            variant="destructive"
            size="sm"
            onClick={handleCancel}
            disabled={isCancelling}
            aria-label="cancel"
          >
            {t('tasks.cancel')}
          </Button>
        )}
      </div>

      {/* Feed */}
      <div
        ref={feedRef}
        className="flex-1 overflow-y-auto rounded-lg border border-border bg-card p-4 space-y-2 min-h-[400px] max-h-[600px]"
      >
        {lines.map((line, i) => (
          <div key={`${line.id}-${i}`} className="flex gap-3 items-start text-sm">
            <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-mono font-semibold ${line.badgeClass}`}>
              {t(line.badge as Parameters<typeof t>[0])}
            </span>
            <span className="text-foreground break-words">{line.content}</span>
          </div>
        ))}
        {isActive && lines.length === 0 && (
          <p className="text-muted-foreground text-sm">Connecting…</p>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Confidence bar */}
      {confidence !== null && (
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">{t('tasks.confidence')}</span>
          <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-success rounded-full transition-all duration-500"
              style={{ width: `${confidence * 100}%` }}
            />
          </div>
          <span className="text-muted-foreground">{Math.round(confidence * 100)}%</span>
        </div>
      )}
    </div>
  )
}
