import { test, expect, Page } from '@playwright/test';
import { loginApi, loginPage, API_BASE, HOSTED } from './auth';

// Creates a test-only member in the local E2E database and disables it afterwards. Passwords are synthetic.
const base = API_BASE;
const FIRST = 'e2e-member-first-synthetic', TEMP = 'e2e-member-temp-synthetic', MINE = 'e2e-member-mine-synthetic';

async function signIn(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/login')), page.getByRole('button', { name: 'Sign in' }).click()]);
}

test('Passwords: owner sets a temporary password, the member signs in and changes it', async ({ page, request }) => {
  test.skip(!!HOSTED, 'Creates a user; local E2E database only.');
  await loginApi(request);
  const email = `member.${Date.now()}@e2e.example`;
  const created = await request.post(`${base}/firm/users`, { data: { email, display_name: 'Mo Member', role: 'preparer', initial_password: FIRST } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const memberId = (await created.json()).id as string;
  try {
    await loginPage(page);
    await page.goto('/firm');
    page.once('dialog', dialog => dialog.accept(TEMP));
    const [reset] = await Promise.all([
      page.waitForResponse(r => r.url().includes(`/firm/users/${memberId}/password`)),
      page.getByTestId('team-member').filter({ hasText: email }).getByRole('button', { name: 'Reset password' }).click(),
    ]);
    expect(reset.ok(), await reset.text()).toBeTruthy();

    await page.getByRole('button', { name: 'Sign out' }).click();
    await page.waitForURL(/\/login/);
    await signIn(page, email, TEMP);
    await page.getByTestId('firm-name').click();
    await page.waitForURL(/\/account/);
    await page.getByLabel('Current password').fill(TEMP);
    await page.getByLabel('New password', { exact: true }).fill(MINE);
    await page.getByLabel('Repeat new password').fill(MINE);
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByTestId('password-changed')).toContainText('Password changed');

    await page.getByRole('button', { name: 'Sign out' }).click();
    await page.waitForURL(/\/login/);
    await signIn(page, email, MINE);
    await expect(page.getByTestId('my-role')).toHaveText('preparer');
  } finally {
    await loginApi(request);
    await request.patch(`${base}/firm/users/${memberId}`, { data: { is_active: false } }).catch(() => undefined);
  }
});
