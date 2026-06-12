import { notFound } from 'next/navigation'
import { TaskFeed } from '@/components/task-feed'
import { HitlPanel } from '@/components/tasks/HitlPanel'
import { AgentTeamSection } from '@/components/tasks/AgentTeamSection'

type Task = { id: string; goal: string; status: string }

async function getTask(taskId: string): Promise<Task | null> {
  // Use internal URL for server-side fetches (Docker internal network)
  const internalUrl = process.env.AGENTIS_INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
  try {
    const res = await fetch(
      `${internalUrl}/api/v1/tasks/${taskId}`,
      { cache: 'no-store' }
    )
    if (res.status === 404) return null
    // Auth failures or network errors: render the page and let client components handle auth
    if (!res.ok) return { id: taskId, goal: '', status: 'unknown' }
    return res.json()
  } catch {
    // Network error (e.g., wrong internal URL): still render the page
    return { id: taskId, goal: '', status: 'unknown' }
  }
}

export default async function TaskPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>
}) {
  const { id } = await params
  const task = await getTask(id)
  if (!task) notFound()

  return (
    <div className="h-full">
      <TaskFeed taskId={task.id} status={task.status} goal={task.goal} />
      <HitlPanel taskId={task.id} />
      <AgentTeamSection taskId={task.id} initialStatus={task.status} />
    </div>
  )
}
