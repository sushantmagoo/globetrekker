import { api, refreshAccessToken } from './client'
import type {
  Comment,
  JournalCard,
  JournalDetail,
  JournalEdit,
  JournalUpdate,
  Me,
  Notification,
  Page,
  Profile,
  TokenOut,
  UserSummary,
  Visibility,
} from './types'
import { useSession } from '../stores/session'

// ---------- auth ----------
async function startSession(tokenOut: TokenOut): Promise<Me> {
  useSession.getState().setToken(tokenOut.access_token)
  const me = await api<Me>('/me')
  useSession.getState().setUser(me)
  return me
}

export const auth = {
  signup: (data: { email: string; password: string; username: string; display_name: string }) =>
    api<TokenOut>('/auth/signup', { method: 'POST', body: data }).then(startSession),
  login: (data: { email: string; password: string }) =>
    api<TokenOut>('/auth/login', { method: 'POST', body: data }).then(startSession),
  logout: async () => {
    try {
      await api<void>('/auth/logout', { method: 'POST' })
    } finally {
      useSession.getState().clear()
    }
  },
}

/** Restore a session from the refresh cookie on app start. */
export async function bootstrapSession(): Promise<void> {
  const token = await refreshAccessToken()
  if (!token) {
    useSession.getState().clear()
    return
  }
  try {
    useSession.getState().setUser(await api<Me>('/me'))
  } catch {
    useSession.getState().clear()
  }
}

export async function reloadMe(): Promise<Me> {
  const me = await api<Me>('/me')
  useSession.getState().setUser(me)
  return me
}

// ---------- me / users ----------
export const me = {
  update: (data: Partial<Pick<Me, 'display_name' | 'bio' | 'home_country' | 'website_url'>> & {
    default_visibility?: Visibility
  }) => api<Me>('/me', { method: 'PATCH', body: data }),
  changePassword: (current_password: string, new_password: string) =>
    api<void>('/me/password', { method: 'PATCH', body: { current_password, new_password } }),
  remove: () => api<void>('/me', { method: 'DELETE' }),
  drafts: () => api<JournalCard[]>('/me/drafts'),
  bookmarks: () => api<JournalCard[]>('/me/bookmarks'),
}

export const users = {
  get: (username: string) => api<Profile>(`/users/${encodeURIComponent(username)}`),
  journals: (username: string, cursor?: string | null) =>
    api<Page<JournalCard>>(`/users/${encodeURIComponent(username)}/journals`, {
      query: { cursor },
    }),
  followers: (username: string, cursor?: string | null) =>
    api<Page<UserSummary>>(`/users/${encodeURIComponent(username)}/followers`, {
      query: { cursor },
    }),
  following: (username: string, cursor?: string | null) =>
    api<Page<UserSummary>>(`/users/${encodeURIComponent(username)}/following`, {
      query: { cursor },
    }),
  follow: (username: string) =>
    api<void>(`/users/${encodeURIComponent(username)}/follow`, { method: 'PUT' }),
  unfollow: (username: string) =>
    api<void>(`/users/${encodeURIComponent(username)}/follow`, { method: 'DELETE' }),
}

// ---------- journals ----------
export const journals = {
  create: () => api<{ id: string; slug: string; version: number }>('/journals', { method: 'POST' }),
  read: (slug: string, t?: string | null) =>
    api<JournalDetail>(`/journals/${encodeURIComponent(slug)}`, { query: { t } }),
  getForEdit: (id: string) => api<JournalEdit>(`/journals/${id}/edit`),
  update: (id: string, data: JournalUpdate) =>
    api<JournalEdit>(`/journals/${id}`, { method: 'PATCH', body: data }),
  publish: (id: string) => api<JournalEdit>(`/journals/${id}/publish`, { method: 'POST' }),
  unpublish: (id: string) => api<JournalEdit>(`/journals/${id}/unpublish`, { method: 'POST' }),
  rotateShareToken: (id: string) =>
    api<JournalEdit>(`/journals/${id}/share-token`, { method: 'POST' }),
  remove: (id: string) => api<void>(`/journals/${id}`, { method: 'DELETE' }),
  like: (id: string, t?: string | null) =>
    api<void>(`/journals/${id}/like`, { method: 'PUT', query: { t } }),
  unlike: (id: string) => api<void>(`/journals/${id}/like`, { method: 'DELETE' }),
  bookmark: (id: string, t?: string | null) =>
    api<void>(`/journals/${id}/bookmark`, { method: 'PUT', query: { t } }),
  unbookmark: (id: string) => api<void>(`/journals/${id}/bookmark`, { method: 'DELETE' }),
}

export const comments = {
  list: (journalId: string, t?: string | null) =>
    api<Comment[]>(`/journals/${journalId}/comments`, { query: { t } }),
  add: (journalId: string, body: string, parent_id?: string | null, t?: string | null) =>
    api<Comment>(`/journals/${journalId}/comments`, {
      method: 'POST',
      body: { body, parent_id },
      query: { t },
    }),
  edit: (id: string, body: string) =>
    api<Comment>(`/comments/${id}`, { method: 'PATCH', body: { body } }),
  remove: (id: string) => api<void>(`/comments/${id}`, { method: 'DELETE' }),
}

// ---------- feeds ----------
export interface ExploreFilters {
  sort: 'recent' | 'trending'
  tag?: string
  country?: string
}

export const feed = {
  home: (cursor?: string | null) => api<Page<JournalCard>>('/feed/home', { query: { cursor } }),
  explore: (filters: ExploreFilters, cursor?: string | null) =>
    api<Page<JournalCard>>('/feed/explore', { query: { ...filters, cursor } }),
}

// ---------- notifications ----------
export const notifications = {
  list: (cursor?: string | null) =>
    api<Page<Notification>>('/notifications', { query: { cursor } }),
  unreadCount: () => api<{ count: number }>('/notifications/unread-count'),
  markRead: (ids?: string[]) =>
    api<void>('/notifications/read', { method: 'POST', body: { ids: ids ?? null } }),
}
