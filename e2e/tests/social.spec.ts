import { expect, test } from '@playwright/test'
import { publishJournal, signUpViaApi } from './helpers'

test('a reader follows, likes and comments; the author is notified', async ({ browser }) => {
  const authorContext = await browser.newContext()
  const authorPage = await authorContext.newPage()
  const author = await signUpViaApi(authorPage, 'author')
  const title = `Night train to Hanoi ${Date.now()}`
  const journal = await publishJournal(authorPage.request, author, { title, visibility: 'followers' })

  const readerContext = await browser.newContext()
  const reader = await readerContext.newPage()
  await signUpViaApi(reader, 'reader')

  // Followers-only: hidden until the reader follows the author.
  await reader.goto(`/j/${journal.slug}`)
  await expect(reader.getByText('Journal not found')).toBeVisible()

  await reader.goto(`/u/${author.username}`)
  await reader.getByRole('button', { name: 'Follow', exact: true }).click()
  await expect(reader.getByRole('button', { name: 'Following', exact: true })).toBeVisible()

  // Now it shows up in the reader's home feed and can be opened.
  await reader.goto('/')
  await reader.getByRole('heading', { name: title }).click()
  await expect(reader.getByRole('heading', { level: 1, name: title })).toBeVisible()

  await reader.getByRole('button', { name: '0' }).click() // like button shows the count
  await expect(reader.getByRole('button', { name: '1' })).toBeVisible()

  await reader.getByLabel('Share your thoughts').fill('What a ride!')
  await reader.getByRole('button', { name: 'Post' }).click()
  await expect(reader.locator('.comment-text', { hasText: 'What a ride!' })).toBeVisible()

  // Like and comment persist across reloads.
  await reader.reload()
  await expect(reader.getByRole('button', { name: '1' })).toBeVisible()
  await expect(reader.locator('.comment-text', { hasText: 'What a ride!' })).toBeVisible()

  // The author sees follow, like and comment notifications.
  await authorPage.goto('/notifications')
  await expect(authorPage.getByText('started following you')).toBeVisible()
  await expect(authorPage.getByText(/liked/)).toBeVisible()
  await expect(authorPage.getByText(/commented on/)).toBeVisible()

  await authorContext.close()
  await readerContext.close()
})
