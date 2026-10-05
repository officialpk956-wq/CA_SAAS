import { test, expect } from '@playwright/test';
import { loginApi, loginPage, API_BASE } from './auth';
import path from 'node:path';

const root = path.resolve(__dirname, '../..');

test('Client requests: reminder draft with an upload link; the client uploads without logging in', async ({ page, request, browser }) => {
  await loginApi(request);
  const client = await (await request.post(`${API_BASE}/clients`, { data: { name: `Synthetic requests ${Date.now()}` } })).json();
  const reg = await (await request.post(`${API_BASE}/clients/${client.id}/registrations`, { data: { gstin: 'DEMO-REQ' } })).json();
  const period = await (await request.post(`${API_BASE}/registrations/${reg.id}/periods`, { data: { period_code: '2026-08' } })).json();
  await loginPage(page);

  await page.goto(`/clients/${client.id}`);
  await page.getByLabel('Client email').fill('owner@client.example');
  await page.getByLabel('Client WhatsApp number').fill('+91 98765 43210');
  await page.getByRole('button', { name: 'Save contact' }).click();
  await expect(page.getByTestId('client-contact')).toContainText('Saved.');

  await page.goto(`/periods/${period.id}/workspace`);
  await page.getByRole('button', { name: 'Draft reminder' }).click();
  const draft = page.getByTestId('reminder-draft');
  await expect(draft).toContainText('sales register for August 2026');
  await expect(draft.getByRole('link', { name: 'Open in email' })).toHaveAttribute('href', /^mailto:owner%40client\.example\?subject=/);
  await expect(draft.getByRole('link', { name: 'Open in WhatsApp' })).toHaveAttribute('href', /^https:\/\/wa\.me\/919876543210\?text=/);
  const body = await draft.locator('pre').innerText();
  const salesLink = body.match(/sales register[^\n]*?(https?:\/\/\S+\/u\/[A-Za-z0-9_-]+)/)![1];

  // A fresh browser context has no session cookie: the link must work without logging in.
  const anon = await browser.newContext();
  const clientPage = await anon.newPage();
  await clientPage.goto(salesLink);
  await expect(clientPage).not.toHaveURL(/\/login/);
  await expect(clientPage.getByText(/asks .* for the sales register/)).toBeVisible();
  await clientPage.getByLabel('File to upload').setInputFiles(path.join(root, 'sample_data/sales_v1/sales_register.csv'));
  await clientPage.getByRole('button', { name: 'Upload', exact: true }).click();
  await expect(clientPage.getByTestId('upload-done')).toContainText('was received');
  await anon.close();

  await page.reload();
  await expect(page.getByTestId('upload-link').filter({ hasText: 'sales link · used 1/5' })).toBeVisible();
  const batches = await (await request.get(`${API_BASE}/periods/${period.id}/sales-imports`)).json();
  expect(batches).toHaveLength(1);
  expect(batches[0].status).toBe('preview');
});
