import { test, expect } from '@playwright/test';
import { E2E_EMAIL, E2E_PASSWORD, API_BASE, WEB_BASE, HOSTED } from './auth';

test('Portal requires login: redirect, wrong password, sign in, sign out', async ({ page, request }) => {
  // Signed out: every page redirects to the login page, remembering where you were going.
  await page.goto('/knowledge');
  await expect(page).toHaveURL(/\/login\?next=%2Fknowledge/);
  await expect(page.getByRole('heading', { name: 'Sign in to your firm' })).toBeVisible();
  // The API refuses data without a session, both directly and through the app's proxy.
  expect((await request.get(`${API_BASE}/clients`)).status()).toBe(401);
  expect((await page.request.get('/api/clients')).status()).toBe(401);

  await page.getByLabel('Email').fill(E2E_EMAIL);
  await page.getByLabel('Password').fill('not-the-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.locator('form').getByRole('alert')).toHaveText('Email or password is incorrect.');

  await page.getByLabel('Password').fill(E2E_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/knowledge$/);
  await expect(page.getByTestId('firm-name')).toHaveText('GST Helper Demo CA Firm');
  const cookie = (await page.context().cookies()).find(c => c.name === 'gsth_session');
  expect(cookie?.httpOnly).toBeTruthy();
  expect(cookie?.sameSite).toBe('Strict');
  if (HOSTED) expect(cookie?.secure).toBeTruthy();  // HTTPS-only cookie on the hosted site
  expect(await page.evaluate(() => document.cookie)).not.toContain('gsth_session');  // not readable by page scripts

  // A crafted "next" pointing to another site is ignored.
  await page.goto('/login?next=//evil.example');
  await page.getByLabel('Email').fill(E2E_EMAIL);
  await page.getByLabel('Password').fill(E2E_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(`${WEB_BASE}/`);

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto('/');
  await expect(page).toHaveURL(/\/login/);
  expect((await page.request.get('/api/clients')).status()).toBe(401);
});
