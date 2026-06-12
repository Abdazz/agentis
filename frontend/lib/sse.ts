import { apiFetch } from './api'

const BACKOFF_DELAYS = [1000, 2000, 4000, 8000, 30000]
const TERMINAL_EVENTS = new Set(['task_completed', 'task_failed'])

export type SSEEvent = {
  id: string
  type: string
  data: unknown
}

export type SSECallbacks = {
  onEvent: (event: SSEEvent) => void
  onError?: (attempt: number) => void
  onDone?: () => void
}

export function parseSSEBlock(block: string): SSEEvent | null {
  if (!block.trim()) return null
  let id = ''
  let type = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('id: ')) id = line.slice(4).trim()
    else if (line.startsWith('event: ')) type = line.slice(7).trim()
    else if (line.startsWith('data: ')) data += (data ? '\n' : '') + line.slice(6)
  }
  if (!data) return null
  let parsed: unknown = data
  try { parsed = JSON.parse(data) } catch { /* keep as string */ }
  return { id, type, data: parsed }
}

/** Returns true if a terminal event was received (stream complete), false if stream closed naturally. */
async function readStream(
  url: string,
  lastId: string | null,
  callbacks: SSECallbacks,
  signal: AbortSignal
): Promise<boolean> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (lastId) headers['Last-Event-ID'] = lastId

  const res = await apiFetch(url, { headers, signal })
  if (!res.ok) throw new Error(`SSE ${res.status}`)
  if (!res.body) throw new Error('No response body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''
    for (const block of parts) {
      const event = parseSSEBlock(block)
      if (!event) continue
      callbacks.onEvent({ ...event })
      if (TERMINAL_EVENTS.has(event.type)) {
        callbacks.onDone?.()
        return true
      }
    }
  }
  return false
}

export function connectSSE(url: string, callbacks: SSECallbacks): () => void {
  let closed = false
  let attempt = 0
  let lastId: string | null = null
  let controller = new AbortController()

  const wrappedCallbacks: SSECallbacks = {
    ...callbacks,
    onEvent: (event) => {
      attempt = 0
      if (event.id) lastId = event.id
      callbacks.onEvent(event)
    },
  }

  async function connect() {
    try {
      const terminal = await readStream(url, lastId, wrappedCallbacks, controller.signal)
      // Stream closed naturally without a terminal event — reconnect immediately
      if (!terminal && !closed) {
        controller = new AbortController()
        connect()
      }
    } catch (err) {
      if (closed) return
      const delay = BACKOFF_DELAYS[Math.min(attempt, BACKOFF_DELAYS.length - 1)]
      callbacks.onError?.(attempt)
      attempt++
      setTimeout(() => {
        if (!closed) {
          controller = new AbortController()
          connect()
        }
      }, delay)
    }
  }

  connect()

  return () => {
    closed = true
    controller.abort()
  }
}
