import { test, expect, Page, APIRequestContext } from '@playwright/test';
import { loginApi, loginPage, API_BASE, expectNoPageOverflow } from './auth';
import path from 'node:path';
import fs from 'node:fs';

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
  const client = await ok(request.post(`${base}/clients`, { data: { name: `Synthetic IMS ${Date.now()}` } }));
  const reg = await ok(request.post(`${base}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-IMS' } }));
  const period = await ok(request.post(`${base}/registrations/${reg.id}/periods`, { data: { period_code: '2026-08' } }));
  const ids: Record<string, string> = {};
  for (const [type, file] of [['purchase', 'purchase_register.csv'], ['statement', 'gstr2b_demo.csv']]) {
    ids[type] = (await ok(request.post(`${base}/periods/${period.id}/imports?source_type=${type}`, { multipart: { file: { name: file, mimeType: 'text/csv', buffer: fs.readFileSync(path.join(root, 'sample_data/v1', file)) } } }))).id;
    await ok(request.post(`${base}/imports/${ids[type]}/commit?acknowledge_invalid=true&note=Synthetic`));
  }
  const run = await ok(request.post(`${base}/periods/${period.id}/reconciliation-runs`, { data: { purchase_batch_id: ids.purchase, statement_batch_id: ids.statement } }));
  return { period: period.id as string, run: run.id as string };
}

test('IMS inbox: bulk-accept exact matches, reject one invoice, and the ITC pre-fill follows', async ({ page, request }) => {
  const setup = await prepare(request);
  await loginPage(page);
  await page.goto(`/periods/${setup.period}/worksheet`);
  await page.getByRole('link', { name: 'IMS inbox' }).click();
  await expect(page.getByTestId('ims-row')).toHaveCount(19);
  await page.getByLabel('IMS note').fill('Matched against books');
  await post(page, '/ims', () => page.getByRole('button', { name: /Accept exact matches with no action \(7\)/ }).click());
  await expect(page.getByTestId('ims-STMT-001')).toContainText('accept');
  await page.getByLabel('IMS note').fill('Supplier disputes this invoice');
  await post(page, '/ims', () => page.getByLabel('IMS action for STMT-001').selectOption('reject'));
  await expect(page.getByTestId('ims-STMT-001')).toContainText('reject');
  await expect(page.getByTestId('ims-STMT-001')).toContainText('Supplier disputes this invoice');
  await expect(page.getByTestId('ims-counts')).toContainText('6');  // accepted after one was rejected

  const sugg = await ok(request.get(`${base}/runs/${setup.run}/itc-suggestions`));
  expect(sugg.counts.claim).toBe(6);
  expect(sugg.suggestions.some((s: { reason: string }) => s.reason.includes('STMT-001 rejected in IMS'))).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page);
});

test('GSTR-2B JSON: converted on upload, with a report of what was not imported', async ({ page, request }) => {
  await loginApi(request);
  const client = await ok(request.post(`${base}/clients`, { data: { name: `Synthetic 2B ${Date.now()}` } }));
  const reg = await ok(request.post(`${base}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-2B' } }));
  const period = await ok(request.post(`${base}/registrations/${reg.id}/periods`, { data: { period_code: '2026-08' } }));
  await loginPage(page);
  await page.goto(`/periods/${period.id}/workspace`);
  await post(page, '/imports/gstr2b', () => page.getByLabel('GSTR-2B JSON').setInputFiles(path.join(root, 'tests/fixtures/gstr2b_v1/sample_gstr2b.json')));
  const report = page.getByTestId('gstr2b-conversion');
  await expect(report).toContainText('3 invoice(s) converted');
  await expect(report).toContainText('reverse charge');
  await expect(report).toContainText('2B-0002 (P)');
  await expect(page.getByTestId('batch-statement')).toContainText('3');
});
