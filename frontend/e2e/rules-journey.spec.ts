import { test, expect, Page, APIRequestContext } from '@playwright/test';
import { loginApi, loginPage, worksheetStep, API_BASE } from './auth';
import path from 'node:path';
import fs from 'node:fs';

// Rules are organisation-wide in the shared E2E database, so this journey only creates client-specific rules
// and a legal rule that cannot change other journeys' results (zero warning days), which it retires again.
const root = path.resolve(__dirname, '../..');
const base = API_BASE;
async function post(page: Page, part: string, action: () => Promise<unknown>) {
  const [response] = await Promise.all([page.waitForResponse(r => r.url().includes(part) && r.request().method() === 'POST' && r.status() !== 307), action()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json().catch(() => null);
}
async function ok(res: Promise<import('@playwright/test').APIResponse>) { const r = await res; expect(r.ok(), await r.text()).toBeTruthy(); return r.json(); }

async function prepare(request: APIRequestContext) {
  await loginApi(request);
  const client = await ok(request.post(`${base}/clients`, { data: { name: `Synthetic rules ${Date.now()}` } }));
  const reg = await ok(request.post(`${base}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-RULES' } }));
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
  const suggestions = (await ok(request.get(`${base}/runs/${run.id}/itc-suggestions`))).suggestions;
  await ok(request.post(`${base}/runs/${run.id}/itc-decisions`, { data: { note: 'Synthetic pre-fill', items: suggestions.map((s: { result_id: string; decision: string }) => ({ result_id: s.result_id, decision: s.decision })) } }));
  return { clientId: client.id as string, clientName: client.name as string, period: period.id as string, sales: sales.id as string, run: run.id as string };
}

test('Knowledge: reminders gate approval, frequencies are explicit, legal values need CA confirmation', async ({ page, request }) => {
  const setup = await prepare(request);
  await loginPage(page);
  await page.goto('/knowledge');

  // A reminder for this client, confirmed by a person.
  await page.getByLabel('Rule client').selectOption(setup.clientId);
  await page.getByLabel('Rule note').fill('Confirm cash payment received before filing, from Aug 2026');
  await post(page, '/knowledge-rules/draft', () => page.getByRole('button', { name: 'Draft rule' }).click());
  let proposed = page.getByTestId('proposed-rule').filter({ hasText: setup.clientName });
  await expect(proposed.getByLabel('Rule kind')).toHaveValue('reminder');
  await post(page, '/confirm', () => proposed.getByRole('button', { name: 'Confirm rule' }).click());
  await expect(page.getByTestId('active-rule').filter({ hasText: setup.clientName })).toContainText('Reminder · every month from 2026-08');

  // A quarterly adjustment: parsed frequency and end month are shown and editable before confirming.
  await page.getByLabel('Rule client').selectOption(setup.clientId);
  await page.getByLabel('Rule note').fill('Quarterly RCM on legal fees Rs. 900.00 SGST from 2026-06 until Mar 2027');
  await post(page, '/knowledge-rules/draft', () => page.getByRole('button', { name: 'Draft rule' }).click());
  proposed = page.getByTestId('proposed-rule').filter({ hasText: 'Quarterly RCM' });
  await expect(proposed.getByLabel('Rule frequency')).toHaveValue('quarterly');
  await expect(proposed.getByLabel('Rule effective to')).toHaveValue('2027-03');
  await post(page, '/confirm', () => proposed.getByRole('button', { name: 'Confirm rule' }).click());
  await expect(page.getByTestId('active-rule').filter({ hasText: 'Quarterly RCM' }).first()).toContainText('every quarter from 2026-06 to 2027-03');

  // Legal register: off until confirmed with a source and the checkbox; then retired again.
  const deadline = page.getByTestId('legal-itc_claim_deadline');
  const alreadyActive = await deadline.getByText('Not configured').count() === 0;
  if (alreadyActive) await post(page, '/retire', () => deadline.getByRole('button', { name: 'Retire' }).click());
  await expect(deadline).toContainText('Not configured');
  await deadline.getByLabel('ITC claim deadline day').fill('30');
  await deadline.getByLabel('ITC claim deadline month').fill('11');
  await deadline.getByLabel('ITC claim deadline warn_days').fill('0');
  await deadline.getByLabel('ITC claim deadline source').fill('Browser test value, not law');
  await deadline.getByLabel('ITC claim deadline applies from').fill('2026-04');
  await expect(deadline.getByRole('button', { name: 'Confirm rule' })).toBeDisabled();
  await deadline.getByLabel('ITC claim deadline checked').check();
  await post(page, '/legal-rules/itc_claim_deadline/confirm', () => deadline.getByRole('button', { name: 'Confirm rule' }).click());
  await expect(deadline).toContainText('Confirmed · from 2026-04');
  await expect(deadline).toContainText('Browser test value, not law');
  await post(page, '/retire', () => deadline.getByRole('button', { name: 'Retire' }).click());
  await expect(deadline).toContainText('Not configured');

  // Worksheet: the quarterly rule does not apply in August; the reminder blocks approval until checked.
  await page.goto(`/periods/${setup.period}/worksheet`);
  await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
  await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
  await worksheetStep(page, 'Adjustments');
  await expect(page.getByTestId('client-rules')).toHaveCount(0);
  await worksheetStep(page, 'Live worksheet');
  await expect(page.getByTestId('blockers')).toContainText('reminder(s) to acknowledge');
  await worksheetStep(page, 'Drafts & approval');
  const reminder = page.getByTestId('reminder');
  await expect(reminder).toContainText('To check');
  await reminder.getByPlaceholder('What did you check?').fill('Bank statement shows the payment');
  await post(page, '/acknowledge', () => reminder.getByRole('button', { name: 'Mark as checked' }).click());
  await expect(reminder).toContainText('Checked');
  await worksheetStep(page, 'Live worksheet');
  await expect(page.getByTestId('no-blockers')).toBeVisible();
  await post(page, '/tax-drafts', () => page.getByRole('button', { name: 'Save draft snapshot' }).click());
  await worksheetStep(page, 'Drafts & approval');
  await page.getByLabel('Approval note').fill('Reminder checked; approving');
  await post(page, '/approve', () => page.getByRole('button', { name: 'Approve draft' }).click());
  await expect(page.getByTestId('draft-state')).toHaveText('Approved');

  await page.goto(`/history?period_id=${setup.period}`);
  await expect(page.getByTestId('audit-row').filter({ hasText: 'reminder acknowledged' })).toBeVisible();
});
