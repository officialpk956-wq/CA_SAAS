import { test, expect, Page } from '@playwright/test';
import { loginPage, expectNoPageOverflow } from './auth';
import path from 'node:path';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const root = path.resolve(__dirname, '../..');
async function post(page: Page, part: string, action: () => Promise<unknown>) {
  const [response] = await Promise.all([page.waitForResponse(r => r.url().includes(part) && r.request().method() === 'POST' && r.status() !== 307), action()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}
test('Complete reconciliation pipeline with persistence and workbook evidence', async ({page}, testInfo) => {
  const unique = Date.now().toString();
  const name = `Synthetic browser client ${unique}`;
  await loginPage(page);
  await page.goto('/clients');
  await page.locator('#name').fill(name);
  await post(page, '/clients', ()=>page.getByRole('button', {name:'Add Client'}).click());
  await page.getByText(name, {exact:true}).click();
  await page.locator('#gstin').fill(`DEMO-${unique}`);
  await page.locator('#legal_name').fill('Synthetic browser registration');
  await post(page,'/registrations',()=>page.getByRole('button',{name:'Add Registration',exact:true}).click());
  await page.getByPlaceholder('2026-08').fill('2026-08');
  await post(page,'/periods',()=>page.getByRole('button',{name:'Create Period'}).click());
  await page.getByText('2026-08',{exact:true}).click();
  await expect(page.getByRole('heading',{name:'Period 2026-08'})).toBeVisible();

  // Real invalid schema request must produce actionable UI feedback.
  await page.getByLabel('purchase CSV').setInputFiles({name:'bad.csv',mimeType:'text/csv',buffer:Buffer.from('wrong,header\n1,2\n')});
  await expect(page.getByTestId('batch-purchase').getByRole('alert')).toContainText('Missing required headers');

  const ids: Record<string,string> = {};
  for (const [type,file] of [['purchase','purchase_register.csv'],['statement','gstr2b_demo.csv']]) {
    const card=page.getByTestId(`batch-${type}`);
    const batch=await post(page,'/imports',()=>page.getByLabel(`${type} CSV`).setInputFiles(path.join(root,'sample_data/v1',file)));
    ids[type]=batch.id;
    await card.getByText('Preview source rows and validation').click();
    await expect(card.getByRole('table')).toBeVisible();
    await expect(card.getByRole('button',{name:'Commit Import'})).toBeDisabled();
    await card.getByRole('checkbox').check();
    await card.getByLabel(`${type} acknowledgement note`).fill('Reviewed intentionally invalid synthetic records.');
    await post(page,'/commit',()=>card.getByRole('button',{name:'Commit Import'}).click());
    await expect(card.getByText('Committed',{exact:true})).toBeVisible();
  }
  await page.getByLabel('purchase version',{exact:true}).selectOption(ids.purchase);
  await page.getByLabel('statement version',{exact:true}).selectOption(ids.statement);
  await post(page,'/reconciliation-runs',()=>page.getByRole('button',{name:'Run Reconciliation'}).click());
  await expect(page.getByRole('heading',{name:'Reconciliation',exact:true})).toBeVisible();
  const expected=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/reconciliation_v1/expected_summary.json'),'utf8'));
  await expect(page.getByTestId('matched-count')).toHaveText(String(expected.matched_pair_count));
  for (const status of ['duplicate_candidate','validation_error','amount_mismatch']) {
    await page.keyboard.press('Escape');
    await page.getByLabel('Finding',{exact:true}).selectOption(status);
    await page.getByRole('button',{name:'Inspect',exact:true}).first().click();
    await expect(page.getByTestId('result-detail')).toContainText(status);
  }
  const reviewNote=`Reviewed evidence ${unique}`;
  await page.getByLabel('Decision',{exact:true}).selectOption('explained');
  await page.getByLabel('Resolution note').fill(reviewNote);
  await post(page,'/resolve',()=>page.getByRole('button',{name:'Save Resolution'}).click());
  await expect(page.getByTestId('result-detail')).toContainText(reviewNote);
  await page.reload();
  await page.getByLabel('Finding',{exact:true}).selectOption('amount_mismatch');
  await page.getByRole('button',{name:'Inspect',exact:true}).first().click();
  await expect(page.getByTestId('result-detail')).toContainText(reviewNote);
  await page.getByLabel('Decision',{exact:true}).selectOption('unresolved');
  await page.getByLabel('Resolution note').fill('Reopened for follow-up');
  await post(page,'/resolve',()=>page.getByRole('button',{name:'Save Resolution'}).click());
  await expect(page.getByTestId('result-detail')).toContainText(reviewNote);
  await expect(page.getByTestId('result-detail')).toContainText('Reopened for follow-up');
  await page.keyboard.press('Escape');
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Export Working Paper'}).click()]);
  const workbook=testInfo.outputPath('working-paper.xlsx');await download.saveAs(workbook);
  execFileSync('python',['-c',`from openpyxl import load_workbook; import sys; w=load_workbook(sys.argv[1]); assert len(w.sheetnames)==8; assert w['Purchase Records'].max_row==21; assert w['Statement Records'].max_row==21; assert w['Review History'].max_row==3; assert not any(c.data_type=='f' for s in w for r in s for c in r)`,workbook]);
  await page.screenshot({path:testInfo.outputPath('desktop-review.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('heading',{name:'Reconciliation',exact:true})).toBeVisible();
  await expectNoPageOverflow(page);
  await page.screenshot({path:testInfo.outputPath('mobile-review.png'),fullPage:true});
  await page.getByRole('link',{name:'Back to period'}).click();
  await expect(page.getByText('Run history',{exact:true})).toBeVisible();
  await expect(page.getByRole('link').filter({hasText:/^[a-f0-9-]{36}$/})).toHaveCount(1);
  await page.getByLabel('purchase version',{exact:true}).selectOption(ids.purchase);
  await page.getByRole('link',{name:'Review purchase categories'}).click();
  await page.getByRole('button',{name:'Review category',exact:true}).first().click();
  await post(page,'/category-suggestion',()=>page.getByRole('button',{name:'Get suggestion'}).click());
  await expect(page.getByTestId('category-suggestion')).toContainText('abstained');
  await page.getByLabel('Manual category',{exact:true}).selectOption('Packaging');
  await page.getByLabel('Category review note',{exact:true}).fill('Synthetic manual category review');
  await page.getByRole('checkbox').check();
  await post(page,'/category-decisions',()=>page.getByRole('button',{name:'Save manual category'}).click());
  await expect(page.getByTestId('category-detail')).toContainText('Synthetic manual category review');
  await page.reload();
  await page.getByRole('button',{name:'Review category',exact:true}).first().click();
  await expect(page.getByTestId('category-detail')).toContainText('Approved category: Packaging');
  await post(page,'/category-suggestion',()=>page.getByRole('button',{name:'Get suggestion'}).click());
  await expect(page.getByTestId('category-detail')).toContainText('approved_rule');
  await page.getByLabel('Category review note',{exact:true}).fill('Mapping suggestion reviewed');
  await post(page,'/category-decisions',()=>page.getByRole('button',{name:'Accept suggestion'}).click());
  await expect(page.getByTestId('category-detail')).toContainText('Mapping suggestion reviewed');
  await page.keyboard.press('Escape');
  await post(page,'/deactivate',()=>page.getByRole('button',{name:'Deactivate mapping'}).click());
  await expect(page.getByTestId('mapping')).toContainText('From 2026-08-01');
  await expect(page.getByTestId('mapping')).toContainText('Inactive');
  await expectNoPageOverflow(page);
  await page.screenshot({path:testInfo.outputPath('mobile-categories.png'),fullPage:true});

});
