import { describe, it, expect, vi, beforeEach } from 'vitest'

// We import apiFetch and useAuthStore after resetting modules to ensure they
// share the same Zustand store instance (fresh per test).
let apiFetch: typeof import('../api').apiFetch
let useAuthStore: typeof import('../auth').useAuthStore

const mockFetch = vi.fn()

beforeEach(async () => {
  vi.resetAllMocks()
  vi.stubGlobal('fetch', mockFetch)
  // Re-import to pick up fresh module state (resets `refreshing` singleton)
  vi.resetModules()
  // Import auth first so api.ts picks up the same instance
  useAuthStore = (await import('../auth')).useAuthStore
  apiFetch = (await import('../api')).apiFetch
  // Ensure store starts clean
  useAuthStore.setState({ accessToken: null })
})

describe('apiFetch', () => {
  it('attaches Authorization header when token is set', async () => {
    useAuthStore.setState({ accessToken: 'tok_abc' })
    mockFetch.mockResolvedValueOnce(new Response('{}', { status: 200 }))

    await apiFetch('/api/v1/tasks')

    const [, init] = mockFetch.mock.calls[0]
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer tok_abc')
  })

  it('does not attach Authorization header when no token', async () => {
    mockFetch.mockResolvedValueOnce(new Response('{}', { status: 200 }))

    await apiFetch('/api/v1/tasks')

    const [, init] = mockFetch.mock.calls[0]
    expect((init.headers as Headers).get('Authorization')).toBeNull()
  })

  it('retries with new token after 401 + successful refresh', async () => {
    useAuthStore.setState({ accessToken: 'expired_tok' })
    // First call returns 401
    mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }))
    // Refresh call returns new token
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'new_tok' }), { status: 200 })
    )
    // Retry call succeeds
    mockFetch.mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }))

    const res = await apiFetch('/api/v1/tasks')

    expect(mockFetch).toHaveBeenCalledTimes(3)
    expect(res.status).toBe(200)
    expect(useAuthStore.getState().accessToken).toBe('new_tok')
  })

  it('clears auth and returns 401 response when refresh fails', async () => {
    useAuthStore.setState({ accessToken: 'expired_tok' })
    mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }))
    mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }))

    const res = await apiFetch('/api/v1/tasks')

    expect(res.status).toBe(401)
    expect(useAuthStore.getState().accessToken).toBeNull()
  })
})
