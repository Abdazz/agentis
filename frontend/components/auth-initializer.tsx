'use client'

import { useEffect } from 'react'
import { useAuthStore } from '@/lib/auth'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export function AuthInitializer() {
  const setAccessToken = useAuthStore((s) => s.setAccessToken)

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.access_token) setAccessToken(data.access_token as string)
      })
      .catch(() => { /* unauthenticated — no token set */ })
  }, [setAccessToken])

  return null
}
