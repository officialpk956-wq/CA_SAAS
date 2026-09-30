import { test, expect, Page, APIRequestContext } from '@playwright/test';
import { loginApi, loginPage, worksheetStep, expectNoPageOverflow, API_BASE } from './auth';
import path from 'node:path';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const root = path.resolve(__dirname, '../..');
const base = API_BASE;
async function post(page: Page, part: string, action: () => Promise<unknown>) {
  const [response] = await Promise.all([page.waitForResponse(r => r.url().includes(part) && r.request().method() === 'POST' && r.status() !== 307), action()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}
async function ok(res: Promise<import('@playwright/test').APIResponse>) { const r = await res; expect(r.ok(), await r.text()).toBeTruthy(); return r.json(); }

// Inputs are prepared through the API (their screens have their own journeys); the worksheet itself is driven in the browser.
async function prepare(request: APIRequestContext) {
  await loginApi(request);
  const client = await ok(request.post(`${base}/clients`, { data: { name: `Synthetic worksheet ${Date.now()}` } }));
  const clientName: string = client.name;
  const reg = await ok(request.post(`${base}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-WORKSHEET' } }));
  const period = await ok(request.post(`${base}/registrations/${reg.id}/periods`, { data: { period_code: '2026-08' } }));
  const sales = await ok(request.post(`${base}/periods/${period.id}/sales-imports`, { multipart: { file: { name: 'sales.csv', mimeType: 'text/csv', buffer: fs.readFileSync(path.join(root, 'sample_data/sales_v1/sales_register.csv')) } } }));
  await ok(request.post(`${base}/sales-imports/${sales.id}/commit`, { data: { acknowledge_blocked: true, note: 'Synthetic' } }));
  const rows = (await ok(request.get(`${base}/sales-imports/${sales.id}?limit=100`))).items;
  for (const row of rows) await ok(request.post(`${base}/sales-imports/${sales.id}/rows/${row.id}/review`, { data: { decision: row.validation_status === 'ready' ? 'reviewed' : 'excluded', note: 'Synthetic' } }));
  const ids: Record<string, string> = {};
  for (const [type, file] of [['purchase', 'purchase_register.csv'], ['statement', 'gstr2b_demo.csv']]) {
    ids[type] = (await ok(request.post(`${base}/periods/${period.id}/imports?source_type=${type}`, { multipart: { file: { name: file, mimeType: 'text/csv', buffer: fs.readFileSync(path.join(root, 'sample_data/v1', file)) } } }))).id;
    await ok(request.post(`${base}/imports/${ids[type]}/commit?acknowledge_invalid=true&note=Synthetic`));
  }
  const run = await ok(request.post(`${base}/periods/${period.id}/reconciliation-runs`, { data: { purchase_batch_id: ids.purchase, statement_batch_id: ids.statement } }));
  return { period: period.id, sales: sales.id, run: run.id, salesRows: rows, clientName };
}

test('Tax worksheet: ITC decisions, adjustments, approval, invalidation, reopening and export', async ({ page, request }, testInfo) => {
  const setup = await prepare(request);
  await loginPage(page);
  const expected = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/calc_v1/cases.json'), 'utf8')).integration_case.expected;
  await page.goto(`/periods/${setup.period}/workspace`);
  await page.getByRole('link', { name: 'Tax worksheet and approval' }).click();
  await expect(page.getByRole('heading', { name: 'Tax Worksheet', exact: true })).toBeVisible();
  await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
  await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
  await worksheetStep(page, 'Live worksheet');
  await expect(page.getByTestId('blockers')).toContainText('no ITC decision');
  await worksheetStep(page, 'ITC decisions');

  // Claim only PUR-001's exact match; everything else is explicitly not claimed.
  await page.getByLabel('ITC decision note').fill('Synthetic ITC review');
  const pur1 = page.locator('tr', { hasText: 'PUR-001' }).filter({ hasText: 'matched' });
  await post(page, '/itc-decisions', () => pur1.getByRole('combobox').selectOption('claim'));
  await expect(pur1.locator('td').nth(3)).toHaveText('claim');
  await page.getByLabel('ITC decision note').fill('Remaining results not claimed in this synthetic draft');
  await post(page, '/itc-decisions', () => page.getByRole('button', { name: /Mark all undecided as not claimed/ }).click());
  await expect(page.getByRole('button', { name: /Mark all undecided as not claimed \(0\)/ })).toBeDisabled();

  await worksheetStep(page, 'Adjustments');
  await page.getByLabel('Adjustment amount').fill('5.00');
  await page.getByLabel('Adjustment note').fill('Synthetic reverse charge');
  await post(page, '/adjustments', () => page.getByRole('button', { name: 'Add adjustment' }).click());
  await page.getByLabel('Adjustment type').selectOption('other_liability');
  await page.getByLabel('Adjustment tax head').selectOption('igst');
  await page.getByLabel('Adjustment amount').fill('1000.00');
  await page.getByLabel('Adjustment note').fill('Keyed in error');
  await post(page, '/adjustments', () => page.getByRole('button', { name: 'Add adjustment' }).click());
  await page.getByLabel('Void reason').fill('Entered by mistake');
  await post(page, '/void', () => page.getByTestId('adjustment').filter({ hasText: '1000.00' }).getByRole('button', { name: 'Void' }).click());
  await expect(page.getByTestId('adjustment').filter({ hasText: '1000.00' })).toContainText('void: Entered by mistake');

  await worksheetStep(page, 'Live worksheet');
  await expect(page.getByTestId('no-blockers')).toBeVisible();
  for (const [head, values] of Object.entries(expected) as [string, Record<string, string>][])
    for (const [key, value] of Object.entries(values)) await expect(page.getByTestId(`live-${key}-${head}`)).toHaveText(value);

  await post(page, '/tax-drafts', () => page.getByRole('button', { name: 'Save draft snapshot' }).click());
  await worksheetStep(page, 'Drafts & approval');
  await expect(page.getByTestId('draft-state')).toHaveText('Draft');
  await page.getByLabel('Approval note').fill('Synthetic approval for demo');
  await post(page, '/approve', () => page.getByRole('button', { name: 'Approve draft' }).click());
  await expect(page.getByTestId('draft-state')).toHaveText('Approved');
  await page.reload();
  await worksheetStep(page, 'Drafts & approval');
  await expect(page.getByTestId('draft-state')).toHaveText('Approved');
  await expect(page.getByTestId('draft-net-cgst')).toHaveText(expected.cgst.net);

  // A later sales review change makes the approval out of date; the snapshot keeps its figures.
  const reviewed = (await ok(request.get(`${base}/sales-imports/${setup.sales}?status=ready`))).items[0];
  await ok(request.post(`${base}/sales-imports/${setup.sales}/rows/${reviewed.id}/review`, { data: { decision: 'unresolved', note: 'Recheck after approval', previous_review_id: reviewed.previous_review_id } }));
  await page.reload();
  await worksheetStep(page, 'Drafts & approval');
  await expect(page.getByTestId('draft-state')).toHaveText('Approved — out of date (inputs changed)');
  await expect(page.getByTestId('draft-net-cgst')).toHaveText(expected.cgst.net);
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export draft workbook' }).click()]);
  const workbook = testInfo.outputPath('tax-worksheet.xlsx'); await download.saveAs(workbook);
  execFileSync('python', ['-c', `from openpyxl import load_workbook; import sys; w=load_workbook(sys.argv[1]); m=dict(w['Metadata'].iter_rows(min_row=2,values_only=True)); assert m['state']=='approved_stale', m['state']; l={r[0]:r for r in w['Worksheet'].iter_rows(min_row=2,values_only=True)}; assert l['cgst'][-1]=='${expected.cgst.net}'; assert l['sgst'][-1]=='${expected.sgst.net}'; assert not any(c.data_type=='f' for s in w for r in s for c in r)`, workbook]);

  await page.getByLabel('Filing reference').fill('DEMO-ARN-0001');
  await page.getByLabel('Filed on').fill('2026-09-20');
  await post(page, '/filing-evidence', () => page.getByRole('button', { name: 'Record filing reference (user-reported)' }).click());
  await expect(page.getByTestId('filing-evidence')).toContainText('user-reported, not verified');
  await page.getByLabel('Reopen reason').fill('Sales row reopened after approval');
  await post(page, '/reopen', () => page.getByRole('button', { name: 'Reopen approval' }).click());
  await expect(page.getByTestId('draft-state')).toHaveText('Reopened');

  await page.getByRole('link', { name: 'History for this period' }).click();
  await expect(page.getByRole('heading', { name: 'History & audit' })).toBeVisible();
  for (const action of ['tax draft approved', 'tax approval reopened', 'adjustment voided', 'itc decided', 'filing evidence recorded'])
    await expect(page.getByTestId('audit-row').filter({ hasText: action }).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('history-desktop.png'), fullPage: true });

  await page.goto(`/periods/${setup.period}/worksheet`);
  await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
  await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
  await worksheetStep(page, 'Live worksheet');
  await expect(page.getByTestId('blockers')).toContainText('pending review');

  // Re-review the row, draft, then change an input: the UI must refuse approval until a fresh draft exists.
  const reopened = (await ok(request.get(`${base}/sales-imports/${setup.sales}?status=ready`))).items.find((r: { id: string }) => r.id === reviewed.id);
  await ok(request.post(`${base}/sales-imports/${setup.sales}/rows/${reviewed.id}/review`, { data: { decision: 'reviewed', note: 'Confirmed again', previous_review_id: reopened.previous_review_id } }));
  await page.reload();
  await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
  await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
  await worksheetStep(page, 'Live worksheet');
  await expect(page.getByTestId('no-blockers')).toBeVisible();
  await post(page, '/tax-drafts', () => page.getByRole('button', { name: 'Save draft snapshot' }).click());
  await worksheetStep(page, 'Drafts & approval');
  await expect(page.getByRole('button', { name: 'Approve draft' })).toBeVisible();
  await worksheetStep(page, 'Adjustments');
  await page.getByLabel('Adjustment type').selectOption('other_credit');
  await page.getByLabel('Adjustment tax head').selectOption('sgst');
  await page.getByLabel('Adjustment amount').fill('1.00');
  await page.getByLabel('Adjustment note').fill('Late synthetic credit');
  await post(page, '/adjustments', () => page.getByRole('button', { name: 'Add adjustment' }).click());
  await worksheetStep(page, 'Drafts & approval');
  await expect(page.getByTestId('draft-outdated')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve draft' })).toHaveCount(0);
  await worksheetStep(page, 'Live worksheet');
  await post(page, '/tax-drafts', () => page.getByRole('button', { name: 'Save draft snapshot' }).click());
  await worksheetStep(page, 'Drafts & approval');
  await expect(page.getByTestId('draft-outdated')).toHaveCount(0);
  await expect(page.getByTestId('draft-net-sgst')).toHaveText('21.50');
  await page.getByLabel('Approval note').fill('Re-approved after reopening');
  await post(page, '/approve', () => page.getByRole('button', { name: 'Approve draft' }).click());
  await expect(page.getByTestId('draft-state')).toHaveText('Approved');
  await page.screenshot({ path: testInfo.outputPath('worksheet-desktop.png'), fullPage: true });

  // The Board reflects the recorded state and links back into the worksheet.
  await page.getByRole('link', { name: 'The Board' }).first().click();
  const boardRow = page.getByTestId('board-row').filter({ hasText: setup.clientName });
  await expect(boardRow).toContainText('Sales reviewed');
  await expect(boardRow).toContainText('Reconciled · ITC decided');
  await expect(boardRow).toContainText('Approved');
  await boardRow.getByRole('link', { name: /worksheet: Approved/ }).click();
  await expect(page.getByRole('heading', { name: 'Tax Worksheet', exact: true })).toBeVisible();
  await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
  await page.getByLabel('Worksheet reconciliation run').selectOption(setup.run);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('worksheet-mobile.png'), fullPage: true });
});
