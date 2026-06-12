import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../api', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '../api'
import { connectSSE, parseSSEBlock } from '../sse'

const mockApiFetch = vi.mocked(apiFetch)

function makeStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

describe('parseSSEBlock', () => {
  it('parses id, event, data fields', () => {
    const result = parseSSEBlock('id: 5\nevent: think\ndata: {"content":"hello"}')
    expect(result).toEqual({ id: '5', type: 'think', data: { content: 'hello' } })
  })

  it('defaults type to message when event line absent', () => {
    const result = parseSSEBlock('id: 1\ndata: hello')
    expect(result).toEqual({ id: '1', type: 'message', data: 'hello' })
  })

  it('returns null for empty block', () => {
    expect(parseSSEBlock('')).toBeNull()
    expect(parseSSEBlock('   ')).toBeNull()
  })
})

describe('connectSSE', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('calls onEvent for each SSE block', async () => {
    const body = makeStream([
      'id: 1\nevent: think\ndata: {"content":"step 1"}\n\n',
      'id: 2\nevent: task_completed\ndata: {"summary":"done"}\n\n',
    ])
    mockApiFetch.mockResolvedValueOnce(new Response(body, { status: 200 }))

    const events: unknown[] = []
    await new Promise<void>((resolve) => {
      connectSSE('/api/v1/tasks/abc/stream', {
        onEvent: (e) => events.push(e),
        onDone: resolve,
      })
    })

    expect(events).toHaveLength(2)
    expect((events[0] as { type: string }).type).toBe('think')
    expect((events[1] as { type: string }).type).toBe('task_completed')
  })

  it('sends Last-Event-ID header on reconnect after error', async () => {
    vi.useFakeTimers()
    const body1 = makeStream(['id: 3\nevent: think\ndata: {}\n\n'])
    const body2 = makeStream(['id: 4\nevent: task_completed\ndata: {}\n\n'])
    mockApiFetch
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(new Response(body1, { status: 200 }))
      .mockResolvedValueOnce(new Response(body2, { status: 200 }))

    const events: unknown[] = []
    await new Promise<void>((resolve) => {
      connectSSE('/api/v1/tasks/abc/stream', {
        onEvent: (e) => events.push(e),
        onDone: resolve,
        onError: () => vi.runAllTimersAsync(),
      })
    })

    // Third call (after body1's stream closed naturally) should include Last-Event-ID: 3
    const [, thirdInit] = mockApiFetch.mock.calls[2]
    expect((thirdInit?.headers as Record<string, string>)?.['Last-Event-ID']).toBe('3')

    vi.useRealTimers()
  })

  it('returns a cleanup function that aborts the stream', () => {
    const controller = new AbortController()
    // Vitest 4.x requires mockImplementation (not mockReturnValue) for constructors called with `new`
    vi.spyOn(window, 'AbortController').mockImplementation(function (this: AbortController) {
      return controller as unknown as AbortController
    } as unknown as typeof AbortController)
    const abortSpy = vi.spyOn(controller, 'abort')

    const body = makeStream([])
    mockApiFetch.mockResolvedValueOnce(new Response(body, { status: 200 }))

    const disconnect = connectSSE('/api/v1/tasks/abc/stream', { onEvent: vi.fn() })
    disconnect()

    expect(abortSpy).toHaveBeenCalled()
  })
})
