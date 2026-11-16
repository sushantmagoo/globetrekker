import { expect, test } from '@playwright/test'
import { signUpViaApi } from './helpers'

test('write a journal, autosave it, publish, and read it logged out', async ({ page, browser }) => {
  await signUpViaApi(page, 'writer')
  const title = `Monsoon in Kerala ${Date.now()}`

  await page.goto('/write')
  await expect(page).toHaveURL(/\/write\/[0-9a-f-]{36}$/)
  const editorUrl = page.url()

  await page.getByLabel('Title', { exact: true }).fill(title)
  const body = page.getByLabel('Journal text')
  await body.click()
  await body.pressSequentially('The backwaters turned silver under the rain.')
  await page.getByRole('button', { name: 'Bold (⌘+B)' }).or(page.getByRole('button', { name: 'Bold (Ctrl+B)' })).click()
  await body.pressSequentially(' Unforgettable.')

  // Autosave (debounced 2 s) persists the draft: reload and it's still there.
  await expect(page.getByText('Saved', { exact: true })).toBeVisible({ timeout: 15_000 })
  await page.reload()
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue(title)
  await expect(page.getByLabel('Journal text')).toContainText('backwaters turned silver')
  await expect(page.getByLabel('Journal text').locator('strong')).toHaveText('Unforgettable.')

  await page.getByRole('button', { name: 'Publish' }).click()
  await expect(page).toHaveURL(/\/j\/monsoon-in-kerala-\d+-[A-Za-z0-9]{6}$/)
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  const journalUrl = page.url()

  // Anyone can read a public journal, without logging in.
  const visitor = await browser.newContext()
  const anon = await visitor.newPage()
  await anon.goto(journalUrl)
  await expect(anon.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await expect(anon.locator('.reader-body strong')).toHaveText('Unforgettable.')
  await anon.goto('/explore')
  await expect(anon.getByRole('heading', { name: title })).toBeVisible()
  await visitor.close()

  // The editor URL still works for the owner after publishing.
  await page.goto(editorUrl)
  await expect(page.getByText('Published', { exact: true })).toBeVisible()
})

test('publishing an empty draft explains what is missing', async ({ page }) => {
  await signUpViaApi(page, 'empty')
  await page.goto('/write')
  await expect(page).toHaveURL(/\/write\//)
  await page.getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByText('Add a title before publishing')).toBeVisible()
})
