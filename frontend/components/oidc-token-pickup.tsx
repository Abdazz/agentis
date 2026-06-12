'use client'

import { useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuthStore } from '@/lib/auth'

/**
 * Reads the `?token=<jwt>` query param injected by the backend after a
 * successful OIDC callback, stores the token in the Zustand auth store,
 * and removes the param from the URL so it doesn't linger in the browser
 * history or get accidentally shared.
 */
export function OidcTokenPickup() {
  const searchParams = useSearchParams()
  const setAccessToken = useAuthStore((s) => s.setAccessToken)

  useEffect(() => {
    const token = searchParams.get('token')
    if (!token) return

    setAccessToken(token)

    // Strip `?token=` from the URL without adding a new history entry.
    const url = new URL(window.location.href)
    url.searchParams.delete('token')
    window.history.replaceState(null, '', url.toString())
  }, [searchParams, setAccessToken])

  return null
}
