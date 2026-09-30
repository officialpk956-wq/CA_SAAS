import { expect, Page, APIRequestContext } from '@playwright/test';

// Test-only login for the dedicated E2E database, set by scripts/serve_e2e.py. Not a real credential.
export const E2E_EMAIL = 'admin@demo.com';
export const E2E_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'e2e-synthetic-login-only';
export const API_BASE = 'http://127.0.0.1:8002';

/** Log the API request context in (for test setup calls made directly to the API). */
export async function loginApi(request: APIRequestContext) {
  const r = await request.post(`${API_BASE}/auth/login`, { data: { email: E2E_EMAIL, password: E2E_PASSWORD } });
  expect(r.ok(), await r.text()).toBeTruthy();
}

/** Log the browser in through the real login page. */
export async function loginPage(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(E2E_EMAIL);
  await page.getByLabel('Password').fill(E2E_PASSWORD);
  await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/login')), page.getByRole('button', { name: 'Sign in' }).click()]);
}

// The tax worksheet shows one ledger step at a time; open one from the ledger index.
export async function worksheetStep(page: Page, label: 'Choose inputs' | 'ITC decisions' | 'Adjustments' | 'Live worksheet' | 'Drafts & approval') {
  await page.getByLabel('Worksheet steps').getByRole('button', { name: label }).click();
}

// Fails with the elements that stick out past the viewport (outside any scrolling/clipping container).
export async function expectNoPageOverflow(page: Page) {
  const offenders = await page.evaluate(() => {
    const out: string[] = [];
    for (const el of Array.from(document.querySelectorAll('body *'))) {
      const r = el.getBoundingClientRect(); if (!r.width || r.right <= innerWidth + 1) continue;
      let p = el.parentElement, clipped = false;
      while (p && !clipped) { clipped = /(auto|scroll|hidden)/.test(getComputedStyle(p).overflowX); p = p.parentElement; }
      if (!clipped) out.push(`${el.tagName.toLowerCase()}.${String(el.getAttribute('class') || '').slice(0, 60)} → ${Math.round(r.right)}px`);
    }
    return document.documentElement.scrollWidth > innerWidth ? out.slice(0, 5) : [];
  });
  expect(offenders, 'elements wider than the viewport').toEqual([]);
}
