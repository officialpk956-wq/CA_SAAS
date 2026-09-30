"""Seed a SYNTHETIC demo roster through the real API, so every row is validated, reconciled and audited.

Eight fictional clients, each left in a different workflow state so the Board shows every status.
All names, references and amounts are invented. Not tax data, not for filing.

Usage (API must be running against the database you want to fill):
    python scripts/seed_demo_data.py [--api http://127.0.0.1:8000] [--email admin@demo.com]
The script signs in as the firm user: it asks for the password privately (or reads GSTH_PASSWORD).
Re-running skips clients that already exist. Generated CSVs are also written to sample_data/demo_v1/.
"""
import argparse
import csv
import getpass
import os
import io
import random
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'sample_data' / 'demo_v1'
SUPPLIERS = ['DEMO-SUP-001', 'DEMO-SUP-002', 'DEMO-SUP-003', 'DEMO-SUP-004', 'DEMO-SUP-005']
# Descriptions per supplier; several contain phrases the mock category model recognises.
PURCHASE_TEXT = {
    'DEMO-SUP-001': ['Printer paper A4 reams', 'Office stationery refill', 'Corrugated cartons for dispatch'],
    'DEMO-SUP-002': ['Laptop repair and servicing', 'Annual software support', 'Network cabling work'],
    'DEMO-SUP-003': ['Freight delivery to warehouse', 'Courier charges for documents', 'Inbound freight delivery'],
    'DEMO-SUP-004': ['Office cleaning services', 'Pest control visit', 'Packaging boxes for dispatch'],
    'DEMO-SUP-005': ['Professional consulting fees', 'Audit support services', 'Advisory retainer'],
}
SALES_TEXT = ['Retail counter sale', 'Online order dispatch', 'Bulk order to distributor', 'Service invoice', 'Annual maintenance contract']
RATES = [Decimal('5'), Decimal('12'), Decimal('18')]
P_HEAD = 'record_id,document_type,supplier_ref,invoice_number,invoice_date,taxable_value,cgst,sgst,igst,cess,invoice_total,description'.split(',')
S_HEAD = P_HEAD[:-1]
SALES_HEAD = 'record_id document_type customer_type customer_ref invoice_number invoice_date supply_scope place_of_supply taxable_value cgst sgst igst cess invoice_total description'.split()

def money(x): return Decimal(x).quantize(Decimal('0.01'), ROUND_HALF_UP)

def amounts(rng, low, high, inter):
    taxable = money(rng.randrange(low, high) * 10)
    rate = rng.choice(RATES)
    if inter: cgst = sgst = Decimal('0.00'); igst = money(taxable * rate / 100)
    else: cgst = sgst = money(taxable * rate / 200); igst = Decimal('0.00')
    cess = Decimal('0.00')
    return [taxable, cgst, sgst, igst, cess, taxable + cgst + sgst + igst + cess]

def to_csv(header, rows):
    buf = io.StringIO(); w = csv.writer(buf, lineterminator='\n'); w.writerow(header)
    for r in rows: w.writerow([format(v, '.2f') if isinstance(v, Decimal) else v for v in r])
    return buf.getvalue().encode()

def purchase_files(rng, period, n):
    """Purchase register + demo statement with realistic, deliberate differences."""
    y, m = period.split('-'); purchases, statement = [], []
    for i in range(1, n + 1):
        sup = SUPPLIERS[(i - 1) % 5]; day = f'{y}-{m}-{rng.randint(1, 28):02d}'
        a = amounts(rng, 20, 900, inter=rng.random() < 0.3)
        inv = f'INV-{m}{i:03d}'
        purchases.append([f'P-{i:03d}', 'invoice', sup, inv, day, *a, rng.choice(PURCHASE_TEXT[sup])])
        statement.append([f'S-{i:03d}', 'invoice', sup, inv, day, *a])
    # Differences an accountant would expect to see:
    statement[1][5] = statement[1][5] + Decimal('100.00'); statement[1][10] = sum(statement[1][5:10])    # taxable mismatch
    statement[3][4] = statement[3][4][:8] + ('15' if statement[3][4][8:] != '15' else '16')               # date conflict
    del statement[5]                                                                                      # books only (supplier yet to file)
    statement.append([f'S-{n + 1:03d}', 'invoice', 'DEMO-SUP-003', f'INV-{m}9{n:02d}', f'{y}-{m}-20', *amounts(rng, 20, 200, False)])  # statement only
    purchases.append([f'P-{n + 1:03d}', *purchases[7][1:]])                                               # duplicate entry in books
    purchases[9][4] = f'{y}-{m}-31' if m in ('02', '04', '06', '09', '11') else f'{y}-13-01'              # invalid date
    return to_csv(P_HEAD, purchases), to_csv(S_HEAD, statement)

def sales_file(rng, period, n):
    y, m = period.split('-'); rows = []
    for i in range(1, n + 1):
        inter = rng.random() < 0.25
        rows.append([f'SAL-{i:03d}', 'invoice', rng.choice(['registered', 'unregistered']), f'DEMO-CUST-{rng.randint(1, 40):03d}', f'INV-S{m}{i:03d}',
                     f'{y}-{m}-{rng.randint(1, 28):02d}', 'domestic', 'DEMO-STATE-02' if inter else 'DEMO-STATE-01', *amounts(rng, 10, 1500, inter), rng.choice(SALES_TEXT)])
    rows[2][13] = rows[2][13] + Decimal('1.00')                     # total does not add up
    rows[6][1] = 'credit_note'                                       # unsupported document type
    rows.append([f'SAL-{n + 1:03d}', *rows[4][1:]])                  # duplicate invoice
    return to_csv(SALES_HEAD, rows)

class Api:
    def __init__(self, base, email):
        self.c = httpx.Client(base_url=base, timeout=120)
        password = os.environ.get('GSTH_PASSWORD') or getpass.getpass(f'Password for {email}: ')
        r = self.c.post('/auth/login', json={'email': email, 'password': password})
        if r.is_error: raise SystemExit(f'Login failed: {r.json().get("detail", r.status_code)}')
    def __call__(self, method, url, **kw):
        r = self.c.request(method, url, **kw)
        if r.is_error: raise SystemExit(f'{method} {url} -> {r.status_code}: {r.text}')
        return r.json()

def build(api, name, reg_ref, plan, rng):
    client = api('POST', '/clients', json={'name': name})
    reg = api('POST', f"/clients/{client['id']}/registrations", json={'gstin': reg_ref, 'legal_name': name})
    for period_code, state in plan:
        period = api('POST', f"/registrations/{reg['id']}/periods", json={'period_code': period_code})['id']
        slug = OUT / reg_ref.lower() / period_code; slug.mkdir(parents=True, exist_ok=True)
        if state == 'awaiting': continue
        sales_bytes = sales_file(rng, period_code, rng.randint(14, 26)); (slug / 'sales_register.csv').write_bytes(sales_bytes)
        sales = api('POST', f'/periods/{period}/sales-imports', files={'file': ('sales_register.csv', sales_bytes, 'text/csv')})['id']
        p_bytes, s_bytes = purchase_files(rng, period_code, rng.randint(16, 24))
        (slug / 'purchase_register.csv').write_bytes(p_bytes); (slug / 'gstr2b_demo.csv').write_bytes(s_bytes)
        batch = {k: api('POST', f'/periods/{period}/imports', params={'source_type': k}, files={'file': (f'{k}.csv', b, 'text/csv')})['id']
                 for k, b in (('purchase', p_bytes), ('statement', s_bytes))}
        if state == 'uploaded': continue
        api('POST', f'/sales-imports/{sales}/commit', json={'acknowledge_blocked': True, 'note': 'Blocked rows noted; corrections requested from client.'})
        rows = api('GET', f'/sales-imports/{sales}', params={'limit': 100})['items']
        review = rows if state != 'sales_partial' else rows[: len(rows) // 2]
        for r in review:
            ready = r['validation_status'] == 'ready'
            api('POST', f"/sales-imports/{sales}/rows/{r['id']}/review", json={'decision': 'reviewed' if ready else 'excluded', 'note': 'Checked against invoice copy.' if ready else 'Excluded pending corrected invoice.'})
        if state == 'sales_partial': continue
        for b in batch.values():
            api('POST', f'/imports/{b}/commit', params={'acknowledge_invalid': True, 'note': 'Invalid rows reported to client for correction.'})
        run = api('POST', f'/periods/{period}/reconciliation-runs', json={'purchase_batch_id': batch['purchase'], 'statement_batch_id': batch['statement']})['id']
        results = api('GET', f'/periods/{period}/reconciliation-runs/{run}/results')
        for r in results:
            if r['status'] == 'amount_mismatch':
                api('POST', f"/runs/{run}/results/{r['result_id']}/resolve", json={'decision': 'investigating', 'note': 'Asked supplier to confirm taxable value.'})
            if r['status'] == 'books_only':
                api('POST', f"/runs/{run}/results/{r['result_id']}/resolve", json={'decision': 'explained', 'note': 'Supplier has not filed yet; follow up next month.'})
        if state == 'itc_pending': continue
        itc = api('GET', f'/runs/{run}/itc-decisions')
        api('POST', f'/runs/{run}/itc-decisions', json={'note': 'Exact matches claimed; differences held back pending supplier confirmation.',
            'items': [{'result_id': r['result_id'], 'decision': 'claim' if r['status'] == 'matched' else ('deferred' if r['status'] == 'books_only' else 'not_claimed')} for r in itc]})
        api('POST', f'/periods/{period}/adjustments', json={'adjustment_type': 'rcm_liability', 'tax_head': 'cgst', 'amount': '450.00', 'note': 'Reverse charge on legal services (synthetic).'})
        api('POST', f'/periods/{period}/adjustments', json={'adjustment_type': 'rcm_liability', 'tax_head': 'sgst', 'amount': '450.00', 'note': 'Reverse charge on legal services (synthetic).'})
        draft = api('POST', f'/periods/{period}/tax-drafts', json={'sales_batch_id': sales, 'run_id': run})
        if draft['blockers']: raise SystemExit(f'{name} {period_code}: unexpected blockers {draft["blockers"]}')
        if state == 'draft': continue
        approval = api('POST', f"/tax-drafts/{draft['id']}/approve", json={'note': 'Reviewed worksheet and supporting schedules.'})['id']
        if state == 'filed':
            api('POST', f'/tax-approvals/{approval}/filing-evidence', json={'arn': f'DEMO-ARN-{reg_ref[-3:]}{period_code[-2:]}', 'filed_on': f'{period_code}-20', 'note': 'Reference typed in by preparer (synthetic).'})
        elif state == 'stale':
            ready = next(r for r in api('GET', f'/sales-imports/{sales}', params={'status': 'ready'})['items'])
            api('POST', f"/sales-imports/{sales}/rows/{ready['id']}/review", json={'decision': 'unresolved', 'note': 'Client sent a revised invoice after approval.', 'previous_review_id': ready['previous_review_id']})
        elif state == 'reopened':
            api('POST', f'/tax-approvals/{approval}/reopen', json={'reason': 'Late purchase invoice received; worksheet needs redraft.'})

# (name, registration reference, [(period, final state)]) — every Board status is represented.
ROSTER = [
    ('Kaveri Retail (synthetic)', 'DEMO-KAVERI-A01', [('2026-07', 'filed'), ('2026-08', 'filed')]),
    ('IndusCart E-commerce (synthetic)', 'DEMO-INDUS-B02', [('2026-07', 'filed'), ('2026-08', 'draft')]),
    ('Nilgiri IT Services (synthetic)', 'DEMO-NILGIRI-C03', [('2026-08', 'stale')]),
    ('Deccan Fabricators (synthetic)', 'DEMO-DECCAN-D04', [('2026-08', 'itc_pending')]),
    ('Malabar Kitchen (synthetic)', 'DEMO-MALABAR-E05', [('2026-08', 'uploaded')]),
    ('Sahyadri Wholesale (synthetic)', 'DEMO-SAHYADRI-F06', [('2026-08', 'sales_partial')]),
    ('Konark Consulting (synthetic)', 'DEMO-KONARK-G07', [('2026-08', 'reopened')]),
    ('Brahmaputra Logistics (synthetic)', 'DEMO-BRAHMA-H08', [('2026-08', 'awaiting')]),
]
DEMO_RULES = [
    ('IndusCart E-commerce (synthetic)', 'Warehouse rent to unregistered landlord: RCM ₹4,500 CGST monthly from Jul 2026',
     {'rule_kind': 'adjustment', 'adjustment_type': 'rcm_liability', 'tax_head': 'cgst', 'amount': '4500.00', 'effective_from': '2026-07'}),
    ('Deccan Fabricators (synthetic)', 'Reverse ITC on exempt scrap sales IGST Rs. 1,250.00 from Aug 2026', None),
    ('Konark Consulting (synthetic)', 'Confirm the client has paid the challan before filing, from Aug 2026', {'rule_kind': 'reminder', 'frequency': 'monthly', 'effective_from': '2026-08'}),
    ('Kaveri Retail (synthetic)', 'Quarterly RCM on legal retainer Rs. 1,800.00 SGST from 2026-09 until Mar 2027',
     {'rule_kind': 'adjustment', 'frequency': 'quarterly', 'adjustment_type': 'rcm_liability', 'tax_head': 'sgst', 'amount': '1800.00', 'effective_from': '2026-09', 'effective_to': '2027-03'}),
]
EXPECTED = {'filed': 'Filed (user-reported)', 'draft': 'Ready for approval', 'stale': 'Approval out of date', 'itc_pending': 'Not started',
            'uploaded': 'Not started', 'sales_partial': 'Not started', 'reopened': 'Reopened — redraft', 'awaiting': 'Not started'}

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0]); parser.add_argument('--api', default='http://127.0.0.1:8000'); parser.add_argument('--email', default='admin@demo.com')
    args = parser.parse_args(); api = Api(args.api, args.email)
    existing = {c['name'] for c in api('GET', '/clients')}
    for i, (name, ref, plan) in enumerate(ROSTER):
        if name in existing: print(f'skip  {name} (exists)'); continue
        build(api, name, ref, plan, random.Random(1000 + i)); print(f'added {name}')
    # Self-check: the Board must show the intended worksheet state for every seeded period.
    board = {(r['client_name'], r['period_code']): r for r in api('GET', '/board')}
    for name, _, plan in ROSTER:
        for period, state in plan:
            row = board[(name, period)]
            assert row['worksheet']['label'] == EXPECTED[state], (name, period, row['worksheet'])
            print(f"  {name[:34]:34} {period}  sales: {row['sales']['label']:26} purchases: {row['purchases']['label']:28} worksheet: {row['worksheet']['label']}")
    # Knowledge rules: one confirmed (appears in IndusCart's worksheet), one awaiting confirmation.
    clients = {c['name']: c['id'] for c in api('GET', '/clients')}
    notes = {r['note'] for r in api('GET', '/knowledge-rules')}
    for name, note, confirm in DEMO_RULES:
        if note in notes: continue
        rule = api('POST', '/knowledge-rules/draft', json={'client_id': clients[name], 'note': note})
        if confirm: api('POST', f"/knowledge-rules/{rule['id']}/confirm", json=confirm)
        print(f'rule  {name}: {"active" if confirm else "proposed"}')
    # A purchase register with accounting-software headers, for demonstrating the column mapper by hand.
    tally = (ROOT / 'sample_data/v1/purchase_register.csv').read_text(encoding='utf-8').replace(','.join(P_HEAD), 'Sl No,Vch Type,Party Code,Bill No,Bill Date,Taxable Amt,CGST Amt,SGST Amt,IGST Amt,Cess Amt,Grand Total,Narration', 1)
    (OUT / 'tally_style_purchase_register.csv').write_text(tally, encoding='utf-8')
    print('Demo roster ready (synthetic data, not for filing).')

if __name__ == '__main__':
    main()
