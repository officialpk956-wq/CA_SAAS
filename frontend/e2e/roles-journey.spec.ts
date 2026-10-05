import { test, expect, Page, APIRequestContext } from '@playwright/test';
import { loginApi, loginPage, worksheetStep, API_BASE, HOSTED } from './auth';
import path from 'node:path';
import fs from 'node:fs';

// Creates a test-only preparer in the local E2E database and disables it again afterwards. Never runs against a hosted site.
const root = path.resolve(__dirname, '../..');
const base = API_BASE;
const PREPARER_PASSWORD = 'e2e-preparer-synthetic-only';
async function post(page: Page, part: string, action: () => Promise<unknown>) {
  const [response] = await Promise.all([page.waitForResponse(r => r.url().includes(part) && ['POST', 'PATCH'].includes(r.request().method()) && r.status() !== 307), action()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json().catch(() => null);
}
async function ok(res: Promise<import('@playwright/test').APIResponse>) { const r = await res; expect(r.ok(), await r.text()).toBeTruthy(); return r.json(); }

async function prepare(request: APIRequestContext) {
  await loginApi(request);
  const client = await ok(request.post(`${base}/clients`, { data: { name: `Synthetic roles ${Date.now()}` } }));
  const reg = await ok(request.post(`${base}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-ROLES' } }));
  const period = await ok(request.post(`${base}/registrations/${reg.id}/periods`, { data: { period_code: '2026-08' } }));
  const sales = await ok(request.post(`${base}/periods/${period.id}/sales-imports`, { multipart: { file: { name: 'sales.csv', mimeType: 'text/csv', buffer: fs.readFileSync(path.join(root, 'sample_data/sales_v1/sales_register.csv')) } } }));
  await ok(request.post(`${base}/sales-imports/${sales.id}/commit`, { data: { acknowledge_blocked: true, note: 'Synthetic' } }));
  for (const row of (await ok(request.get(`${base}/sales-imports/${sales.id}?limit=100`))).items)
    await ok(request.post(`${base}/sales-imports/${sales.id}/rows/${row.id}/review`, { data: { decision: row.validation_status === 'ready' ? 'reviewed' : 'excluded', note: 'Synthetic' } }));
  const ids: Record<string, string> = {};
  for (const [type, file] of [['purchase', 'purchase_register.csv'], ['statement', 'gstr2b_demo.csv']]) {
    ids[type] = (await ok(request.post(`${base}/periods/${period.id}/imports?source_type=${type}`, { multipart: { file: { name: file, mimeType: 'text/csv', buffer: fs.readFileSync(path.join(root, 'sample_data/v1', file)) } } }))).id;
    await ok(request.post(`${base}/imports/${ids[type]}/commit?acknowledge_invalid=true&note=Synthetic`));
  }
  const run = await ok(request.post(`${base}/periods/${period.id}/reconciliation-runs`, { data: { purchase_batch_id: ids.purchase, statement_batch_id: ids.statement } }));
  const results = await ok(request.get(`${base}/runs/${run.id}/itc-decisions`));
  await ok(request.post(`${base}/runs/${run.id}/itc-decisions`, { data: { note: 'Synthetic', items: results.map((r: { result_id: string; status: string }) => ({ result_id: r.result_id, decision: r.status === 'matched' ? 'claim' : 'not_claimed' })) } }));
  return { clientName: client.name as string, period: period.id as string, sales: sales.id as string, run: run.id as string };
}

test('Roles: owner adds a preparer and assigns work; the preparer sees it but cannot approve', async ({ page, request }) => {
  test.skip(!!HOSTED, 'Creates a user; local E2E database only.');
  const setup = await prepare(request);
  const email = `preparer.${Date.now()}@e2e.example`;
  let preparerId: string | undefined;
  try {
    await loginPage(page);
    await page.goto('/firm');
    await page.getByLabel('New member name').fill('Pia Preparer');
    await page.getByLabel('New member email').fill(email);
    await page.getByLabel('New member role').selectOption('preparer');
    await page.getByLabel('New member initial password').fill(PREPARER_PASSWORD);
    preparerId = (await post(page, '/firm/users', () => page.getByRole('button', { name: 'Add to firm' }).click())).id;
    await expect(page.getByTestId('team-member').filter({ hasText: email })).toContainText('Pia Preparer');

    await page.goto(`/periods/${setup.period}/worksheet`);
    await post(page, '/assign', () => page.getByLabel('Assigned to').selectOption(preparerId!));
    await page.goto('/');
    await expect(page.getByTestId('board-row').filter({ hasText: setup.clientName })).toContainText('Pia Preparer');

    // Sign in as the preparer.
    await page.getByRole('button', { name: 'Sign out' }).click();
    await page.waitForURL(/\/login/);
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill(PREPARER_PASSWORD);
    await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/login')), page.getByRole('button', { name: 'Sign in' }).click()]);
    await expect(page.getByTestId('my-role')).toHaveText('preparer');
    await page.getByLabel('Only my work').check();
    await expect(page.getByTestId('board-row')).toHaveCount(1);
    await expect(page.getByTestId('board-row')).toContainText(setup.clientName);

    await page.goto(`/periods/${setup.period}/worksheet`);
    await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
    await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
    await worksheetStep(page, 'Live worksheet');
    await post(page, '/tax-drafts', () => page.getByRole('button', { name: 'Save draft snapshot' }).click());
    await worksheetStep(page, 'Drafts & approval');
    await page.getByLabel('Approval note').fill('Trying to approve my own preparation');
    const approve = page.getByRole('button', { name: 'Approve draft' });
    await expect(approve).toBeDisabled();
    await expect(approve).toHaveAttribute('title', /preparer\) cannot approve/);
    await page.goto('/firm');
    await expect(page.getByText('Only an owner can change people or settings')).toBeVisible();
  } finally {
    if (preparerId) { await loginApi(request); await request.patch(`${base}/firm/users/${preparerId}`, { data: { is_active: false } }).catch(() => undefined); }
  }
});
