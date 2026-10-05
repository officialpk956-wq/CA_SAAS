import { test, expect, Page, APIRequestContext } from '@playwright/test';
import { loginApi, loginPage, worksheetStep, API_BASE } from './auth';
import path from 'node:path';
import fs from 'node:fs';

// Set-off rules are organisation-wide in the shared E2E database: this journey confirms test-only values and
// always retires them again (finally), so other journeys never see them.
const root = path.resolve(__dirname, '../..');
const base = API_BASE;
const configA: string[] = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/setoff_v1/cases.json'), 'utf8')).configs.A;
async function post(page: Page, part: string, action: () => Promise<unknown>) {
  const [response] = await Promise.all([page.waitForResponse(r => r.url().includes(part) && r.request().method() === 'POST' && r.status() !== 307), action()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json().catch(() => null);
}
async function ok(res: Promise<import('@playwright/test').APIResponse>) { const r = await res; expect(r.ok(), await r.text()).toBeTruthy(); return r.json(); }

async function prepare(request: APIRequestContext) {
  await loginApi(request);
  const client = await ok(request.post(`${base}/clients`, { data: { name: `Synthetic setoff ${Date.now()}` } }));
  const reg = await ok(request.post(`${base}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-SETOFF' } }));
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
  // Claim only PUR-001's exact match so the period has real cash payable after set-off.
  const results = await ok(request.get(`${base}/runs/${run.id}/itc-decisions`));
  await ok(request.post(`${base}/runs/${run.id}/itc-decisions`, { data: { note: 'Synthetic', items: results.map((r: { result_id: string; status: string; purchase_record_ids: string[] }) => ({ result_id: r.result_id, decision: r.status === 'matched' && r.purchase_record_ids[0] === 'PUR-001' ? 'claim' : 'not_claimed' })) } }));
  return { period: period.id as string, sales: sales.id as string, run: run.id as string };
}

async function confirmLegal(page: Page, title: string, key: string, fill: () => Promise<void>) {
  const card = page.getByTestId(`legal-${key}`);
  await expect(card.getByText(/Not configured|Confirmed · from/)).toBeVisible();  // wait for the card to load before branching
  if (await card.getByText('Not configured').count() === 0) await post(page, '/retire', () => card.getByRole('button', { name: 'Retire' }).click());
  await fill();
  await card.getByLabel(`${title} source`).fill('Browser test configuration, not law');
  await card.getByLabel(`${title} applies from`).fill('2026-04');
  await card.getByLabel(`${title} checked`).check();
  await expect(card.getByRole('button', { name: 'Confirm rule' })).toBeEnabled();
  await post(page, `/legal-rules/${key}/confirm`, () => card.getByRole('button', { name: 'Confirm rule' }).click());
  await expect(card).toContainText('Confirmed · from 2026-04');
}

test('Set-off: not computed until CA rules are confirmed; then cash payable follows them', async ({ page, request }) => {
  const setup = await prepare(request);
  await loginPage(page);
  try {
    await page.goto(`/periods/${setup.period}/worksheet`);
    await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
    await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
    await worksheetStep(page, 'Adjustments');
    await page.getByLabel('Adjustment type').selectOption('opening_credit');
    await page.getByLabel('Adjustment tax head').selectOption('igst');
    await page.getByLabel('Adjustment amount').fill('50.00');
    await page.getByLabel('Adjustment note').fill('Ledger balance brought forward (user-reported)');
    await post(page, '/adjustments', () => page.getByRole('button', { name: 'Add adjustment' }).click());
    await worksheetStep(page, 'Live worksheet');
    await expect(page.getByTestId('live-opening_credit-igst')).toHaveText('50.00');
    await expect(page.getByTestId('live-setoff')).toContainText('Set-off not computed');

    await page.goto('/knowledge');
    await confirmLegal(page, 'Credit utilisation order (set-off)', 'credit_utilisation_order', () => page.getByLabel('Credit utilisation order (set-off) steps').fill(configA.join('\n')));
    await confirmLegal(page, 'Rounding of cash payable', 'payment_rounding', async () => {
      await page.getByLabel('Rounding of cash payable multiple').fill('1.00');
      await page.getByLabel('Rounding of cash payable direction').selectOption('half_up');
    });

    await page.goto(`/periods/${setup.period}/worksheet`);
    await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
    await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
    await worksheetStep(page, 'Live worksheet');
    // Liability IGST 90.00, CGST 112.50, SGST 112.50; credit PUR-001 CGST/SGST 90.00 + opening IGST 50.00 →
    // cash IGST 40.00, CGST 22.50→23.00, SGST 22.50→23.00 = 86.00 (half-up to the rupee).
    await expect(page.getByTestId('live-total-cash')).toHaveText('₹86.00');
    await expect(page.getByTestId('live-setoff-cash-cgst')).toHaveText('23.00');
    await expect(page.getByTestId('live-setoff-cash_before_rounding-cgst')).toHaveText('22.50');
    await expect(page.getByTestId('live-setoff-cash-igst')).toHaveText('40.00');
    await expect(page.getByTestId('live-setoff')).toContainText('Browser test configuration, not law');
    await post(page, '/tax-drafts', () => page.getByRole('button', { name: 'Save draft snapshot' }).click());
    await worksheetStep(page, 'Drafts & approval');
    await expect(page.getByTestId('draft-total-cash')).toHaveText('₹86.00');
    await page.getByTestId('gstr3b-view').locator('summary').click();
    await expect(page.getByTestId('gstr3b-cash-cgst')).toHaveText('23.00');
    await expect(page.getByTestId('gstr3b-view')).toContainText('not captured');
  } finally {
    for (const key of ['credit_utilisation_order', 'payment_rounding']) await request.post(`${base}/legal-rules/${key}/retire`).catch(() => undefined);
  }
});
