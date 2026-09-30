import { test, expect, Page, APIRequestContext } from '@playwright/test';
import { loginApi, loginPage, worksheetStep, expectNoPageOverflow } from './auth';
import path from 'node:path';
import fs from 'node:fs';

const root = path.resolve(__dirname, '../..');
const base = 'http://127.0.0.1:8002';
async function post(page: Page, part: string, action: () => Promise<unknown>) {
  const [response] = await Promise.all([page.waitForResponse(r => r.url().includes(part) && r.request().method() === 'POST' && r.status() !== 307), action()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json().catch(() => null);
}
async function ok(res: Promise<import('@playwright/test').APIResponse>) { const r = await res; expect(r.ok(), await r.text()).toBeTruthy(); return r.json(); }

// Sales reviewed, statement committed; the purchase file is uploaded in the browser through the column mapper.
async function prepare(request: APIRequestContext) {
  await loginApi(request);
  const client = await ok(request.post(`${base}/clients`, { data: { name: `Synthetic assistants ${Date.now()}` } }));
  const reg = await ok(request.post(`${base}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-ASSIST' } }));
  const period = await ok(request.post(`${base}/registrations/${reg.id}/periods`, { data: { period_code: '2026-08' } }));
  const sales = await ok(request.post(`${base}/periods/${period.id}/sales-imports`, { multipart: { file: { name: 'sales.csv', mimeType: 'text/csv', buffer: fs.readFileSync(path.join(root, 'sample_data/sales_v1/sales_register.csv')) } } }));
  await ok(request.post(`${base}/sales-imports/${sales.id}/commit`, { data: { acknowledge_blocked: true, note: 'Synthetic' } }));
  for (const row of (await ok(request.get(`${base}/sales-imports/${sales.id}?limit=100`))).items)
    await ok(request.post(`${base}/sales-imports/${sales.id}/rows/${row.id}/review`, { data: { decision: row.validation_status === 'ready' ? 'reviewed' : 'excluded', note: 'Synthetic' } }));
  const statement = await ok(request.post(`${base}/periods/${period.id}/imports?source_type=statement`, { multipart: { file: { name: 'gstr2b_demo.csv', mimeType: 'text/csv', buffer: fs.readFileSync(path.join(root, 'sample_data/v1/gstr2b_demo.csv')) } } }));
  await ok(request.post(`${base}/imports/${statement.id}/commit?acknowledge_invalid=true&note=Synthetic`));
  return { clientId: client.id as string, clientName: client.name as string, period: period.id as string, sales: sales.id as string };
}

test('Assistants: column mapper, ITC pre-fill, investigator, follow-ups, knowledge rules, savings, ask and brief', async ({ page, request }, testInfo) => {
  const setup = await prepare(request);
  await loginPage(page);
  // 1. Column mapper: a Tally-style export is rejected, mapped, converted and uploaded through normal validation.
  const tally = fs.readFileSync(path.join(root, 'sample_data/v1/purchase_register.csv'), 'utf8')
    .replace('record_id,document_type,supplier_ref,invoice_number,invoice_date,taxable_value,cgst,sgst,igst,cess,invoice_total,description', 'Sl No,Vch Type,Party Code,Bill No,Bill Date,Taxable Amt,CGST Amt,SGST Amt,IGST Amt,Cess Amt,Grand Total,Narration');
  await page.goto(`/periods/${setup.period}/workspace`);
  const card = page.getByTestId('batch-purchase');
  await card.getByLabel('purchase CSV').setInputFiles({ name: 'tally-export.csv', mimeType: 'text/csv', buffer: Buffer.from(tally) });
  await expect(card.getByRole('alert')).toContainText('Missing required headers');
  const mapper = card.getByTestId('column-mapper');
  await expect(mapper.getByLabel('Source column for invoice_number')).toHaveValue('Bill No');
  const batch = await post(page, '/imports', () => mapper.getByRole('button', { name: 'Convert and upload' }).click());
  expect(batch.invalid_count).toBe(3);
  await card.getByRole('checkbox').check();
  await card.getByLabel('purchase acknowledgement note').fill('Synthetic invalid rows acknowledged');
  await post(page, '/commit', () => card.getByRole('button', { name: 'Commit Import' }).click());
  const imports = await ok(request.get(`${base}/periods/${setup.period}/imports`));
  await page.getByLabel('purchase version', { exact: true }).selectOption(batch.id);
  await page.getByLabel('statement version', { exact: true }).selectOption(imports.find((i: { source_type: string }) => i.source_type === 'statement').id);
  const run = await post(page, '/reconciliation-runs', () => page.getByRole('button', { name: 'Run Reconciliation' }).click());

  // 2. Investigator: explains a books-only finding; the note is only a suggestion until saved.
  await expect(page.getByRole('heading', { name: 'Reconciliation', exact: true })).toBeVisible();
  await page.getByLabel('Finding', { exact: true }).selectOption('amount_mismatch');
  await page.getByRole('button', { name: 'Inspect', exact: true }).first().click();
  const investigator = page.getByTestId('investigator');
  await investigator.getByRole('button', { name: 'Investigate this finding' }).click();
  await expect(investigator).toContainText('differs by');
  await investigator.getByRole('button', { name: 'Use as resolution note' }).click();
  await expect(page.getByLabel('Resolution note')).not.toHaveValue('');
  await post(page, '/resolve', () => page.getByRole('button', { name: 'Save Resolution' }).click());

  // 3. Supplier follow-up drafts: copy-only.
  await expect(page.getByTestId('followup-draft')).toHaveCount(3);
  await expect(page.getByTestId('supplier-followups')).toContainText('INV-106');

  // 4. Knowledge rule: drafted from a note, confirmed by a person.
  await page.goto('/knowledge');
  await page.getByLabel('Rule client').selectOption(setup.clientId);
  await page.getByLabel('Rule note').fill('Rent to unregistered landlord: RCM ₹4,500 CGST monthly from Aug 2026');
  await post(page, '/knowledge-rules/draft', () => page.getByRole('button', { name: 'Draft rule' }).click());
  const proposed = page.getByTestId('proposed-rule').filter({ hasText: setup.clientName });
  await expect(proposed.getByLabel('Rule amount')).toHaveValue('4500.00');
  await expect(proposed.getByLabel('Rule effective from')).toHaveValue('2026-08');
  await post(page, '/confirm', () => proposed.getByRole('button', { name: 'Confirm rule' }).click());
  await expect(page.getByTestId('active-rule').filter({ hasText: setup.clientName })).toBeVisible();

  // 5. Worksheet: accept ITC suggestions with a note, apply the rule, check savings and ask the ledger.
  await page.goto(`/periods/${setup.period}/worksheet`);
  await page.getByLabel('Worksheet sales version').selectOption(setup.sales);
  await page.getByLabel('Worksheet reconciliation run').selectOption(run.id);
  await worksheetStep(page, 'ITC decisions');
  const suggestions = page.getByTestId('itc-suggestions');
  await expect(suggestions).toContainText('7 claim · 3 deferred · 15 not claimed');
  await page.getByLabel('ITC decision note').fill('Accepted pre-fill after review');
  await post(page, '/itc-decisions', () => suggestions.getByRole('button', { name: /Accept 25 suggestion/ }).click());
  await expect(page.getByTestId('itc-suggestions')).toHaveCount(0);
  await worksheetStep(page, 'Adjustments');
  const rules = page.getByTestId('client-rules');
  await post(page, '/apply', () => rules.getByRole('button', { name: 'Apply rule' }).click());
  await expect(rules).toContainText('Applied this period');
  await worksheetStep(page, 'Live worksheet');
  await expect(page.getByTestId('live-liability_adjustments-cgst')).toHaveText('4500.00');
  await expect(page.getByTestId('no-blockers')).toBeVisible();
  await expect(page.getByTestId('saving-waiting_on_supplier')).toContainText('414.00');
  await expect(page.getByTestId('savings-total')).toHaveText('₹4934.00');
  const askPanel = page.getByTestId('ask-ledger');
  await post(page, '/ask', () => askPanel.getByRole('button', { name: 'What is blocking approval?' }).click());
  await expect(page.getByTestId('ask-answer')).toContainText('Nothing is blocking approval');
  await post(page, '/ask', () => askPanel.getByRole('button', { name: 'How much credit is at risk?' }).click());
  await expect(page.getByTestId('ask-answer')).toContainText('₹4934.00');
  await page.screenshot({ path: testInfo.outputPath('assistants-worksheet.png'), fullPage: true });

  // 6. Board: morning brief and savings tile built from records.
  await page.goto('/');
  await expect(page.getByTestId('morning-brief')).toBeVisible();
  await expect(page.getByTestId('credit-at-risk')).toContainText('credit at risk or unclaimed');
  await page.screenshot({ path: testInfo.outputPath('assistants-board.png') });

  // 7. History shows the rule and the accepted suggestions as human actions.
  await page.goto(`/history?period_id=${setup.period}`);
  for (const action of ['rule applied', 'itc decided', 'exception investigating'])
    await expect(page.getByTestId('audit-row').filter({ hasText: action }).first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page);
});
