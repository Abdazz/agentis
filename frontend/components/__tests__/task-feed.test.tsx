import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import type { SSECallbacks } from '@/lib/sse'

vi.mock('@/lib/sse', () => ({
  connectSSE: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
vi.mock('@/i18n/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import { connectSSE } from '@/lib/sse'
import { TaskFeed } from '../task-feed'

const mockConnectSSE = vi.mocked(connectSSE)

describe('TaskFeed', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders think event with THINK badge', async () => {
    let capturedCallbacks: SSECallbacks
    mockConnectSSE.mockImplementation((_url, callbacks) => {
      capturedCallbacks = callbacks
      return () => {}
    })

    render(<TaskFeed taskId="abc-123" status="running" goal="Research task" />)

    act(() => {
      capturedCallbacks!.onEvent({
        id: '1',
        type: 'think',
        data: { content: 'Analyzing the request', tokens: 42 },
      })
    })

    expect(screen.getByText('events.think')).toBeInTheDocument()
    expect(screen.getByText('Analyzing the request')).toBeInTheDocument()
  })

  it('renders tool_call event with TOOL badge', async () => {
    let capturedCallbacks: SSECallbacks
    mockConnectSSE.mockImplementation((_url, callbacks) => {
      capturedCallbacks = callbacks
      return () => {}
    })

    render(<TaskFeed taskId="abc-123" status="running" goal="Research task" />)

    act(() => {
      capturedCallbacks!.onEvent({
        id: '2',
        type: 'tool_call',
        data: { tool: 'web_search', params: { query: 'SaaS competitors' }, call_id: 'c1' },
      })
    })

    expect(screen.getByText('events.tool')).toBeInTheDocument()
    expect(screen.getByText(/web_search/)).toBeInTheDocument()
  })

  it('shows cancel button when status is running', () => {
    mockConnectSSE.mockReturnValue(() => {})
    render(<TaskFeed taskId="abc-123" status="running" goal="Research task" />)
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('does not show cancel button when task is completed', () => {
    mockConnectSSE.mockReturnValue(() => {})
    render(<TaskFeed taskId="abc-123" status="completed" goal="Research task" />)
    expect(screen.queryByRole('button', { name: /cancel/i })).toBeNull()
  })
})
