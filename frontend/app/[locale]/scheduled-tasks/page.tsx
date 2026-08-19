'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  useScheduledTasks,
  useCreateScheduledTask,
  useUpdateScheduledTask,
  useDeleteScheduledTask,
  ScheduledTask,
} from '@/hooks/useScheduledTasks'

const CRON_PRESETS = [
  { label: 'everyDay9am', value: '0 9 * * *' },
  { label: 'everyMonday9am', value: '0 9 * * 1' },
  { label: 'everyHour', value: '0 * * * *' },
  { label: 'firstOfMonth', value: '0 9 1 * *' },
]

function StatusBadge({ sched, t }: { sched: ScheduledTask; t: ReturnType<typeof useTranslations<'scheduledTasks'>> }) {
  if (!sched.is_active) {
    return <Badge variant="secondary">{t('paused')}</Badge>
  }
  if (sched.last_status === 'schedule_error') {
    return <Badge className="bg-destructive/15 text-destructive border-destructive/30">{t('lastRunError')}</Badge>
  }
  return <Badge className="bg-green-500/15 text-green-400 border-green-500/30">{t('active')}</Badge>
}

export default function ScheduledTasksPage() {
  const t = useTranslations('scheduledTasks')
  const { data, isLoading, error } = useScheduledTasks()
  const createSched = useCreateScheduledTask()
  const updateSched = useUpdateScheduledTask()
  const deleteSched = useDeleteScheduledTask()

  const [name, setName] = useState('')
  const [goal, setGoal] = useState('')
  const [cron, setCron] = useState(CRON_PRESETS[0].value)
  const [formError, setFormError] = useState<string | null>(null)

  function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (!name.trim() || !goal.trim() || !cron.trim()) return
    createSched.mutate(
      { name: name.trim(), goal_template: goal.trim(), cron_expression: cron.trim() },
      {
        onSuccess: () => { setName(''); setGoal('') },
        onError: (err) => setFormError((err as Error).message),
      }
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </div>

      <form onSubmit={handleCreate} className="space-y-3 rounded-lg border border-border bg-card p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-sm font-medium">{t('nameLabel')}</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('namePlaceholder')}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">{t('cronLabel')}</label>
            <div className="flex gap-2">
              <Input
                value={cron}
                onChange={(e) => setCron(e.target.value)}
                placeholder="0 9 * * *"
                className="font-mono"
              />
              <select
                className="text-xs rounded-md border border-input bg-background px-2"
                value=""
                onChange={(e) => { if (e.target.value) setCron(e.target.value) }}
              >
                <option value="">{t('presets')}</option>
                {CRON_PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>{t(p.label)}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">{t('goalLabel')}</label>
          <Textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder={t('goalPlaceholder')}
            rows={2}
          />
        </div>
        {formError && <p className="text-sm text-destructive">{formError}</p>}
        <Button type="submit" disabled={createSched.isPending}>
          {createSched.isPending ? t('creating') : t('create')}
        </Button>
      </form>

      {isLoading && <div className="text-muted-foreground text-sm">{t('loading')}</div>}
      {error && <div className="text-destructive text-sm">{(error as Error).message}</div>}

      {!isLoading && !error && (
        <>
          {(!data || data.length === 0) ? (
            <p className="text-sm text-muted-foreground py-8 text-center">{t('empty')}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('colName')}</TableHead>
                  <TableHead>{t('colSchedule')}</TableHead>
                  <TableHead>{t('colStatus')}</TableHead>
                  <TableHead>{t('colNextRun')}</TableHead>
                  <TableHead>{t('colLastRun')}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((sched) => (
                  <TableRow key={sched.id}>
                    <TableCell className="font-medium">{sched.name}</TableCell>
                    <TableCell className="font-mono text-xs">{sched.cron_expression}</TableCell>
                    <TableCell><StatusBadge sched={sched} t={t} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(sched.next_run_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {sched.last_run_at ? new Date(sched.last_run_at).toLocaleString() : t('never')}
                    </TableCell>
                    <TableCell className="flex gap-2 justify-end">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={updateSched.isPending}
                        onClick={() => updateSched.mutate({ id: sched.id, is_active: !sched.is_active })}
                      >
                        {sched.is_active ? t('pause') : t('resume')}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={deleteSched.isPending}
                        onClick={() => deleteSched.mutate(sched.id)}
                      >
                        {t('delete')}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </div>
  )
}
