import { expect, test } from '@playwright/test'

test.describe('stack wiring', () => {
  test('API is healthy through the frontend proxy', async ({ request }) => {
    expect((await request.get('/api/health')).ok()).toBe(true)
    const ready = await request.get('/api/ready')
    expect(ready.ok()).toBe(true)
    expect(await ready.json()).toEqual({ status: 'ok' })
  })

  test('home page renders for visitors @mobile', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Every trip deserves a story.' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign up' })).toBeVisible()
    await expect(page).toHaveTitle(/Globetrekker/)
  })

  test('unknown routes show a 404 page', async ({ page }) => {
    await page.goto('/this/does/not/exist')
    await expect(page.getByText('Page not found')).toBeVisible()
  })

  test('API errors use problem+json', async ({ request }) => {
    const res = await request.get('/api/v1/journals/no-such-journal')
    expect(res.status()).toBe(404)
    expect(res.headers()['content-type']).toContain('application/problem+json')
    expect((await res.json()).title).toBe('Not Found')
  })

  test('link-preview endpoint returns Open Graph HTML', async ({ request }) => {
    const res = await request.get('/api/v1/og/j/no-such-journal')
    expect(res.ok()).toBe(true)
    expect(await res.text()).toContain('property="og:site_name" content="Globetrekker"')
  })
})
