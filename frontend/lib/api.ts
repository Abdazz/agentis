import { useAuthStore } from './auth'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

let refreshing: Promise<string | null> | null = null

async function doRefresh(): Promise<string | null> {
  const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) return null
  const { access_token } = await res.json()
  useAuthStore.getState().setAccessToken(access_token as string)
  return access_token as string
}

async function refreshToken(): Promise<string | null> {
  if (!refreshing) refreshing = doRefresh().finally(() => { refreshing = null })
  return refreshing
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = useAuthStore.getState().accessToken
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })

  if (res.status !== 401) return res

  const newToken = await refreshToken()
  if (!newToken) {
    useAuthStore.getState().clearAuth()
    return res
  }

  headers.set('Authorization', `Bearer ${newToken}`)
  return fetch(`${API_BASE}${path}`, { ...init, credentials: 'include', headers })
}
