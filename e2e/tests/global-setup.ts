import type { FullConfig } from '@playwright/test'

/** Wait until the stack is up: the SPA is served and the API can reach Postgres. */
export default async function globalSetup(config: FullConfig) {
  const base = config.projects[0].use.baseURL ?? 'http://localhost:5173'
  const deadline = Date.now() + 120_000
  let last = ''
  while (Date.now() < deadline) {
    try {
      const [page, ready] = await Promise.all([fetch(base), fetch(`${base}/api/ready`)])
      if (page.ok && ready.ok) return
      last = `page ${page.status}, api ${ready.status}`
    } catch (err) {
      last = String(err)
    }
    await new Promise((r) => setTimeout(r, 2000))
  }
  throw new Error(`Stack at ${base} not ready after 120s (${last}). Is "docker compose up" running?`)
}
