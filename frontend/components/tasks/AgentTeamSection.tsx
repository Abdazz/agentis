'use client'

import { useTranslations } from 'next-intl'
import { Link } from '@/i18n/navigation'
import { useSubtasks, type TaskSummary } from '@/hooks/useSubtasks'

// ─── agent_role badge ─────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  supervisor: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  research:   'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  analysis:   'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  writer:     'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
}
const DEFAULT_ROLE_COLOR = 'bg-muted text-muted-foreground'

// ─── status badge ─────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  running:          'text-primary',
  completed:        'text-success',
  failed:           'text-destructive',
  cancelled:        'text-muted-foreground',
  pending:          'text-muted-foreground',
  submitted:        'text-muted-foreground',
  planning:         'text-primary',
  waiting_for_input: 'text-primary',
}

// ─── SubtaskCard ──────────────────────────────────────────────────────────────

function SubtaskCard({ subtask }: { subtask: TaskSummary }) {
  const t = useTranslations('tasks')
  const roleColor = subtask.agent_role
    ? (ROLE_COLORS[subtask.agent_role] ?? DEFAULT_ROLE_COLOR)
    : DEFAULT_ROLE_COLOR
  const statusColor = STATUS_COLORS[subtask.status] ?? 'text-muted-foreground'
  const isActive = ['submitted', 'planning', 'running', 'waiting_for_input'].includes(subtask.status)
  const truncatedGoal =
    subtask.goal.length > 80 ? subtask.goal.slice(0, 77) + '…' : subtask.goal

  return (
    <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-card gap-3">
      {/* Left: role badge + goal */}
      <div className="flex items-center gap-2 min-w-0 flex-1">
        {subtask.agent_role && (
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-mono font-semibold ${roleColor}`}>
            {subtask.agent_role}
          </span>
        )}
        <span className="text-sm text-foreground truncate" title={subtask.goal} aria-label={t('subtaskGoal')}>
          {truncatedGoal}
        </span>
      </div>

      {/* Right: status + link */}
      <div className="flex items-center gap-3 shrink-0">
        <span className={`text-xs font-medium ${statusColor}`}>
          {isActive ? '● ' : ''}
          {t(`status.${subtask.status}` as Parameters<typeof t>[0])}
        </span>
        <Link
          href={`/tasks/${subtask.id}`}
          className="text-xs text-primary hover:underline"
        >
          {t('viewSubtask')}
        </Link>
      </div>
    </div>
  )
}

// ─── AgentTeamSection ─────────────────────────────────────────────────────────

interface AgentTeamSectionProps {
  taskId: string
  initialStatus: string
}

export function AgentTeamSection({ taskId, initialStatus }: AgentTeamSectionProps) {
  const t = useTranslations('tasks')
  const { data: subtasks, error } = useSubtasks(taskId, initialStatus)

  if (error) {
    return (
      <div className="mt-6">
        <p className="text-sm text-destructive">{(error as Error).message}</p>
      </div>
    )
  }

  if (!subtasks || subtasks.length === 0) return null

  return (
    <div className="mt-6">
      <h2 className="text-sm font-semibold text-foreground mb-3">{t('agentTeam')}</h2>
      <div className="space-y-2">
        {subtasks.map((subtask) => (
          <SubtaskCard key={subtask.id} subtask={subtask} />
        ))}
      </div>
    </div>
  )
}
