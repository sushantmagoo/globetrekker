import { useSession } from '../stores/session'
import type { FieldError, TokenOut } from './types'

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export class ApiError extends Error {
  status: number
  title: string
  detail?: string
  errors: FieldError[]

  constructor(status: number, body: { title?: string; detail?: string; errors?: FieldError[] }) {
    super(body.detail ?? body.title ?? `Request failed (${status})`)
    this.status = status
    this.title = body.title ?? 'Error'
    this.detail = body.detail
    this.errors = body.errors ?? []
  }
}

/** Thrown when the network is unreachable (offline, server down). */
export class NetworkError extends Error {}

type Query = Record<string, string | number | boolean | null | undefined>

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Query
  signal?: AbortSignal
  /** internal: whether a 401 may trigger one refresh + retry */
  retry?: boolean
}

function buildUrl(path: string, query?: Query): string {
  const url = `${API_BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

let refreshing: Promise<string | null> | null = null

/** Exchanges the httpOnly refresh cookie for a new access token. Single-flight. */
export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= (async () => {
    try {
      const res = await fetch(buildUrl('/auth/refresh'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      })
      if (!res.ok) {
        useSession.getState().clear()
        return null
      }
      const data = (await res.json()) as TokenOut
      useSession.getState().setToken(data.access_token)
      return data.access_token
    } catch {
      return null
    }
  })().finally(() => {
    refreshing = null
  })
  return refreshing
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal, retry = true } = opts
  const headers: Record<string, string> = { 'X-Requested-With': 'XMLHttpRequest' }
  const token = useSession.getState().token
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res: Response
  try {
    res = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'include',
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new NetworkError('You appear to be offline')
  }

  if (res.status === 401 && retry && token && !path.startsWith('/auth/')) {
    const fresh = await refreshAccessToken()
    if (fresh) return api<T>(path, { ...opts, retry: false })
  }
  if (!res.ok) {
    let problem: { title?: string; detail?: string; errors?: FieldError[] } = {}
    try {
      problem = await res.json()
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, problem)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** Human-readable message for any error thrown by `api`. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail ?? err.title
  if (err instanceof Error) return err.message
  return 'Something went wrong'
}
