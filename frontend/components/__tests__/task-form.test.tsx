import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TaskForm } from '../task-form'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
vi.mock('@/i18n/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import { apiFetch } from '@/lib/api'
const mockFetch = vi.mocked(apiFetch)

// TaskForm now embeds TemplateModal (task templates, Phase-final), which
// calls useTemplates() — a TanStack Query hook — so it needs a QueryClient
// in the tree, same as task-list.test.tsx already does for TaskList.
function renderWithQueryClient(component: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{component}</QueryClientProvider>)
}

describe('TaskForm', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders goal textarea and submit button', () => {
    renderWithQueryClient(<TaskForm />)
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument()
  })

  it('disables submit when goal is empty', () => {
    renderWithQueryClient(<TaskForm />)
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
  })

  it('enables submit when goal has text', async () => {
    renderWithQueryClient(<TaskForm />)
    await userEvent.type(screen.getByRole('textbox'), 'Research competitors')
    expect(screen.getByRole('button', { name: /submit/i })).toBeEnabled()
  })

  it('rejects files larger than 50 MB', async () => {
    renderWithQueryClient(<TaskForm />)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const bigFile = new File(['x'.repeat(51 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' })
    Object.defineProperty(input, 'files', { value: [bigFile] })
    fireEvent.change(input)
    expect(screen.getByText(/50/)).toBeInTheDocument()
  })

  it('rejects more than 5 files', async () => {
    renderWithQueryClient(<TaskForm />)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = Array.from({ length: 6 }, (_, i) =>
      new File(['x'], `file${i}.txt`, { type: 'text/plain' })
    )
    Object.defineProperty(input, 'files', { value: files })
    fireEvent.change(input)
    expect(screen.getByText(/5/)).toBeInTheDocument()
  })

  it('submits JSON when no files attached', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 'task-123' }), { status: 201 })
    )
    renderWithQueryClient(<TaskForm />)
    await userEvent.type(screen.getByRole('textbox'), 'Research competitors')
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))

    const [path, init] = mockFetch.mock.calls[0]
    expect(path).toBe('/api/v1/tasks')
    expect(init?.method).toBe('POST')
    expect(init?.headers).toMatchObject({ 'Content-Type': 'application/json' })
  })
})
