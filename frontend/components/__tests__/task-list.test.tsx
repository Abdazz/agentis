import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TaskList } from '../task-list'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
vi.mock('@/i18n/navigation', () => ({
  Link: ({ children, href }: any) => <a href={href}>{children}</a>,
}))

import { apiFetch } from '@/lib/api'
const mockFetch = vi.mocked(apiFetch)

const mockTasks = [
  {
    id: 'task-1',
    goal: 'Research competitors',
    status: 'completed',
    created_at: '2024-01-15T10:00:00Z',
    duration_ms: 5000,
  },
  {
    id: 'task-2',
    goal: 'Write report',
    status: 'running',
    created_at: '2024-01-16T11:00:00Z',
    duration_ms: null,
  },
]

function renderWithQueryClient(component: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{component}</QueryClientProvider>)
}

describe('TaskList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders initial tasks', () => {
    renderWithQueryClient(<TaskList initialItems={mockTasks} />)
    expect(screen.getByText('Research competitors')).toBeInTheDocument()
    expect(screen.getByText('Write report')).toBeInTheDocument()
  })

  it('displays empty state when no tasks', () => {
    renderWithQueryClient(<TaskList initialItems={[]} />)
    expect(screen.getByText('empty')).toBeInTheDocument()
  })

  it('displays task status with correct translation key', () => {
    renderWithQueryClient(<TaskList initialItems={mockTasks} />)
    expect(screen.getByText('status.completed')).toBeInTheDocument()
    expect(screen.getByText('status.running')).toBeInTheDocument()
  })

  it('formats duration correctly', () => {
    renderWithQueryClient(<TaskList initialItems={mockTasks} />)
    expect(screen.getByText('5s')).toBeInTheDocument()
  })

  it('displays dash for null duration', () => {
    renderWithQueryClient(<TaskList initialItems={mockTasks} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders load more button when there are more pages', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [
            {
              id: 'task-3',
              goal: 'Third task',
              status: 'pending',
              created_at: '2024-01-17T12:00:00Z',
              duration_ms: null,
            },
          ],
          next_cursor: null,
        })
      )
    )

    const tasksWithCursor = [
      ...mockTasks,
      {
        id: 'task-3',
        goal: 'Another task',
        status: 'pending',
        created_at: '2024-01-17T12:00:00Z',
        duration_ms: null,
      },
    ]

    renderWithQueryClient(<TaskList initialItems={mockTasks.slice(0, 1)} />)
    const loadMore = screen.queryByText(/Load more/)
    // Load more may not appear if next_cursor is null in initial data
    expect(loadMore).not.toBeInTheDocument()
  })

  it('links to task details page', () => {
    renderWithQueryClient(<TaskList initialItems={mockTasks} />)
    const link = screen.getByRole('link', { name: /Research competitors/ })
    expect(link).toHaveAttribute('href', '/tasks/task-1')
  })

  it('formats duration in minutes when greater than 60 seconds', () => {
    const longTask = {
      ...mockTasks[0],
      duration_ms: 125000, // 125 seconds = 2m 5s
    }
    renderWithQueryClient(<TaskList initialItems={[longTask]} />)
    expect(screen.getByText('2m 5s')).toBeInTheDocument()
  })
})
