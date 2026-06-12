import { create } from 'zustand'

function decodeJwtRole(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.role ?? null
  } catch {
    return null
  }
}

interface AuthState {
  accessToken: string | null
  role: string | null
  setAccessToken: (token: string | null) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  role: null,
  setAccessToken: (token) => set({
    accessToken: token,
    role: token ? decodeJwtRole(token) : null,
  }),
  clearAuth: () => set({ accessToken: null, role: null }),
}))
