import { create } from 'zustand'
import type { Me } from '../api/types'

type Status = 'loading' | 'authed' | 'anon'

interface SessionState {
  status: Status
  /** Access token lives in memory only (never localStorage). */
  token: string | null
  user: Me | null
  setToken: (token: string | null) => void
  setUser: (user: Me) => void
  clear: () => void
}

export const useSession = create<SessionState>((set) => ({
  status: 'loading',
  token: null,
  user: null,
  setToken: (token) => set({ token }),
  setUser: (user) => set({ user, status: 'authed' }),
  clear: () => set({ token: null, user: null, status: 'anon' }),
}))
