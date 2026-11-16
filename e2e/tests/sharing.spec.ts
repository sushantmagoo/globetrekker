import { expect, test } from '@playwright/test'
import { publishJournal, signUpViaApi } from './helpers'

test('unlisted journals are only readable with the share link', async ({ page, browser }) => {
  const author = await signUpViaApi(page, 'unlisted')
  const journal = await publishJournal(page.request, author, { title: 'Secret beach', visibility: 'unlisted' })

  // The owner's share modal shows the tokenised link.
  await page.goto(`/j/${journal.slug}`)
  await page.getByRole('button', { name: 'Share' }).click()
  const link = await page.getByLabel('Share link').inputValue()
  expect(link).toContain(`/j/${journal.slug}?t=${journal.share_token}`)
  await expect(page.getByText('Anyone with this link can read the journal')).toBeVisible()

  const visitor = await browser.newContext()
  const anon = await visitor.newPage()
  await anon.goto(`/j/${journal.slug}`)
  await expect(anon.getByText('Journal not found')).toBeVisible()
  await anon.goto(new URL(link).pathname + new URL(link).search)
  await expect(anon.getByRole('heading', { level: 1, name: 'Secret beach' })).toBeVisible()
  // ...and it never shows up in Explore.
  await anon.goto('/explore')
  await expect(anon.getByRole('heading', { name: 'Secret beach' })).toHaveCount(0)
  await visitor.close()
})

test('private journals are invisible to other people', async ({ page, browser }) => {
  const author = await signUpViaApi(page, 'private')
  const journal = await publishJournal(page.request, author, { title: 'Just for me', visibility: 'private' })

  await page.goto(`/j/${journal.slug}`)
  await expect(page.getByRole('heading', { level: 1, name: 'Just for me' })).toBeVisible()

  const otherContext = await browser.newContext()
  const other = await otherContext.newPage()
  await signUpViaApi(other, 'snoop')
  await other.goto(`/j/${journal.slug}?t=${journal.share_token}`)
  await expect(other.getByText('Journal not found')).toBeVisible()
  await otherContext.close()
})

test('link previews show the journal title to crawlers', async ({ page }) => {
  const author = await signUpViaApi(page, 'og')
  const journal = await publishJournal(page.request, author, { title: 'Tea & Trains' })
  const res = await page.request.get(`/api/v1/og/j/${journal.slug}`)
  expect(await res.text()).toContain('property="og:title" content="Tea &amp; Trains by')
})
