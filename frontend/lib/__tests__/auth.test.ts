import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: null })
  })

  it('starts with null token', () => {
    expect(useAuthStore.getState().accessToken).toBeNull()
  })

  it('setAccessToken stores a token', () => {
    useAuthStore.getState().setAccessToken('tok_abc')
    expect(useAuthStore.getState().accessToken).toBe('tok_abc')
  })

  it('clearAuth resets token to null', () => {
    useAuthStore.getState().setAccessToken('tok_abc')
    useAuthStore.getState().clearAuth()
    expect(useAuthStore.getState().accessToken).toBeNull()
  })
})
