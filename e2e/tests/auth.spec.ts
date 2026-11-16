import { expect, test } from '@playwright/test'
import { logOutViaMenu, PASSWORD, uniqueName } from './helpers'

test('sign up, stay logged in across reloads, log out and log back in', async ({ page }) => {
  const username = uniqueName('signup')
  const email = `${username}@example.com`

  await page.goto('/signup')
  await page.getByLabel('Your name').fill('Asha Traveller')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Create account' }).click()

  // New accounts land straight in the editor with a fresh draft.
  await expect(page).toHaveURL(/\/write\/[0-9a-f-]{36}$/)
  await expect(page.getByLabel('Title', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Publish' })).toBeEnabled()

  // The session survives a full reload (refresh-cookie bootstrap).
  await page.reload()
  await expect(page.getByRole('button', { name: 'Account menu' })).toBeVisible()

  await logOutViaMenu(page)
  await page.goto('/write')
  await expect(page).toHaveURL(/\/login$/) // members-only route redirects

  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('wrong-password-here')
  await page.getByRole('button', { name: 'Log in' }).last().click()
  await expect(page.getByText('Incorrect email or password')).toBeVisible()

  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).last().click()
  await expect(page.getByRole('button', { name: 'Account menu' })).toBeVisible()
})

test('sign-up shows field errors for taken usernames', async ({ page, request }) => {
  const username = uniqueName('taken')
  const first = await request.post('/api/v1/auth/signup', {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    data: { email: `${username}@example.com`, password: PASSWORD, username, display_name: 'First' },
  })
  expect(first.status()).toBe(201)

  await page.goto('/signup')
  await page.getByLabel('Your name').fill('Second Person')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Email').fill(`other_${username}@example.com`)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByText('This username is taken')).toBeVisible()
})
