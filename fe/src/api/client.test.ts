import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '../stores/session'
import { api, ApiError, errorMessage, NetworkError, refreshAccessToken } from './client'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('api client', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    useSession.setState({ status: 'anon', token: null, user: null })
  })
  afterEach(() => {
    fetchMock.mockReset()
    vi.unstubAllGlobals()
  })

  it('sends the CSRF header, bearer token and JSON body', async () => {
    useSession.setState({ token: 'tok' })
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }))
    await api('/journals', { method: 'POST', body: { a: 1 }, query: { t: 'x', empty: '' } })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/journals?t=x')
    const headers = init?.headers as Record<string, string>
    expect(headers['X-Requested-With']).toBe('XMLHttpRequest')
    expect(headers.Authorization).toBe('Bearer tok')
    expect(init?.body).toBe('{"a":1}')
    expect(init?.credentials).toBe('include')
  })

  it('turns problem+json responses into ApiError with field errors', async () => {
    fetchMock.mockResolvedValueOnce(
      json(422, { title: 'Validation Error', detail: 'Some fields are invalid', errors: [{ field: 'title', message: 'Required' }] }),
    )
    const err = await api('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(422)
    expect((err as ApiError).errors).toEqual([{ field: 'title', message: 'Required' }])
    expect(errorMessage(err)).toBe('Some fields are invalid')
  })

  it('returns undefined for 204 responses', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(api('/x', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('reports network failures as NetworkError', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api('/x')).rejects.toBeInstanceOf(NetworkError)
  })

  it('refreshes once on 401 and retries the request with the new token', async () => {
    useSession.setState({ token: 'old' })
    fetchMock
      .mockResolvedValueOnce(json(401, { title: 'Unauthorized' }))
      .mockResolvedValueOnce(json(200, { access_token: 'new', token_type: 'bearer', expires_in: 900 }))
      .mockResolvedValueOnce(json(200, { id: 1 }))
    await expect(api('/me')).resolves.toEqual({ id: 1 })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/refresh')
    const retryHeaders = (fetchMock.mock.calls[2][1]?.headers ?? {}) as Record<string, string>
    expect(retryHeaders.Authorization).toBe('Bearer new')
  })

  it('clears the session when refresh fails', async () => {
    useSession.setState({ status: 'authed', token: 'old' })
    fetchMock.mockResolvedValueOnce(json(401, {}))
    await expect(refreshAccessToken()).resolves.toBeNull()
    expect(useSession.getState().status).toBe('anon')
  })

  it('shares a single refresh between concurrent callers', async () => {
    fetchMock.mockResolvedValue(json(200, { access_token: 'new', token_type: 'bearer', expires_in: 900 }))
    const [a, b] = await Promise.all([refreshAccessToken(), refreshAccessToken()])
    expect(a).toBe('new')
    expect(b).toBe('new')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
