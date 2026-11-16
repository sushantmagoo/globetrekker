import { expect, type APIRequestContext, type Page } from '@playwright/test'

const API = '/api/v1'
const XHR = { 'X-Requested-With': 'XMLHttpRequest' }
export const PASSWORD = 'e2e-test-password-123'

/** Unique per test run so tests never collide, even against a reused database. */
export function uniqueName(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 8)
  return `${prefix}_${Date.now().toString(36)}${rand}`.slice(0, 30)
}

export interface TestUser {
  username: string
  email: string
  displayName: string
  token: string
}

/**
 * Sign up through the API using the page's own request context, so the refresh cookie
 * lands in the browser and the next page load is already logged in.
 */
export async function signUpViaApi(page: Page, prefix = 'user'): Promise<TestUser> {
  const username = uniqueName(prefix)
  const user = { username, email: `${username}@example.com`, displayName: `${prefix} ${username.slice(-4)}` }
  const res = await page.request.post(`${API}/auth/signup`, {
    headers: XHR,
    data: { ...user, display_name: user.displayName, password: PASSWORD },
  })
  expect(res.status(), await res.text()).toBe(201)
  const { access_token } = await res.json()
  return { ...user, token: access_token }
}

type Visibility = 'public' | 'followers' | 'unlisted' | 'private'

export interface Journal {
  id: string
  slug: string
  share_token: string
  title: string
}

/** Create and publish a journal through the API (fast setup for tests that aren't about the editor). */
export async function publishJournal(
  request: APIRequestContext,
  user: TestUser,
  { title, body = 'Rain on the tin roof all night.', visibility = 'public' as Visibility } = {} as {
    title: string
    body?: string
    visibility?: Visibility
  },
): Promise<Journal> {
  const auth = { ...XHR, Authorization: `Bearer ${user.token}` }
  const created = await (await request.post(`${API}/journals`, { headers: auth })).json()
  const patched = await request.patch(`${API}/journals/${created.id}`, {
    headers: auth,
    data: {
      version: created.version,
      title,
      visibility,
      content_json: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: body }] }] },
    },
  })
  expect(patched.status(), await patched.text()).toBe(200)
  const published = await request.post(`${API}/journals/${created.id}/publish`, { headers: auth })
  expect(published.status(), await published.text()).toBe(200)
  return published.json()
}

export async function logOutViaMenu(page: Page) {
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: /log out/i }).click()
  await expect(page.getByRole('button', { name: 'Sign up' })).toBeVisible()
}
