from decimal import Decimal
import pytest
from backend.gst_copilot import assist

def rec(rid, side, sup='DEMO-SUP-001', inv='INV-0018', dt='2026-08-10', taxable='1000.00', cgst='90.00', sgst='90.00', igst='0.00', total='1180.00'):
    return {'record_id': rid, 'side': side, 'supplier_ref': sup, 'invoice_number': inv, 'invoice_date': dt,
            'taxable_value': taxable, 'cgst': cgst, 'sgst': sgst, 'igst': igst, 'cess': '0.00', 'invoice_total': total}

@pytest.mark.parametrize('a,b', [('INV/0018', 'inv-18'), ('INV 18', 'INV18'), ('0045', '45'), ('A-08-001', 'A/8/1')])
def test_normalize_invoice_ignores_punctuation_case_and_leading_zeros(a, b):
    assert assist.normalize_invoice(a) == assist.normalize_invoice(b)

def test_normalize_invoice_keeps_different_numbers_apart():
    assert assist.normalize_invoice('INV-180') != assist.normalize_invoice('INV-18')

def test_itc_suggestions_cover_every_finding_and_skip_decided():
    results = [{'result_id': s, 'status': s, 'decision': 'undecided'} for s in assist.ITC_RULES] + [{'result_id': 'x', 'status': 'matched', 'decision': 'claim'}]
    out = {s['result_id']: s['decision'] for s in assist.itc_suggestions(results)}
    assert out['matched'] == 'claim' and out['books_only'] == 'deferred'
    assert all(v == 'not_claimed' for k, v in out.items() if k not in ('matched', 'books_only'))
    assert 'x' not in out

def test_investigator_finds_punctuation_variant_but_never_pairs_by_itself():
    mine = rec('P-1', 'purchase', inv='INV-0018')
    other = [rec('S-9', 'statement', inv='INV/18', dt='2026-08-11'), rec('S-7', 'statement', inv='INV-77', total='50.00')]
    out = assist.investigate({'status': 'books_only'}, [mine], other)
    assert [c['record']['record_id'] for c in out['candidates']] == ['S-9']
    assert any('punctuation' in r for r in out['candidates'][0]['reasons']) and any('1 day' in r for r in out['candidates'][0]['reasons'])
    assert out['candidates'][0]['differences'] == {}

def test_investigator_abstains_when_nothing_similar():
    out = assist.investigate({'status': 'books_only'}, [rec('P-1', 'purchase')], [rec('S-1', 'statement', sup='DEMO-SUP-002', inv='X-1', total='9.00')])
    assert out['candidates'] == [] and 'not filed' in out['findings'][-1]

def test_investigator_spots_tax_head_swap():
    out = assist.investigate({'status': 'amount_mismatch', 'differences': {'cgst': '90.00', 'sgst': '90.00', 'igst': '-180.00'}}, [], [])
    assert any('intra-state vs inter-state' in f for f in out['findings'])

def test_mapping_proposes_aliases_and_rewrites_verbatim():
    content = 'Sl No,Vch Type,Party Code,Bill No,Bill Date,Taxable Amt,CGST Amt,SGST Amt,IGST Amt,Cess Amt,Grand Total,Narration,Extra\n1,invoice,DEMO-SUP-001,B-1,2026-08-01,"1,000.00",90.00,90.00,0.00,0.00,1180.00,Paper,x\n'.encode()
    proposal = assist.propose_mapping(assist.read_headers(content), 'purchase')
    assert proposal['missing_required'] == [] and proposal['mapping']['invoice_number'] == 'Bill No' and proposal['unused_headers'] == ['Extra']
    rows = assist.apply_mapping(content, 'purchase', proposal['mapping']).decode().splitlines()
    assert rows[0] == ','.join(assist.TEMPLATES['purchase'])
    assert '"1,000.00"' in rows[1]  # copied as-is: validation, not the mapper, rejects the comma

def test_mapping_refuses_incomplete_or_reused_columns():
    content = b'a,b\n1,2\n'
    with pytest.raises(ValueError): assist.apply_mapping(content, 'statement', {'record_id': 'a'})
    full = {f: 'a' for f in assist.TEMPLATES['statement']}
    with pytest.raises(ValueError): assist.apply_mapping(content, 'statement', full)

def test_followup_groups_by_supplier_and_totals_credit_at_risk():
    items = [{'supplier_ref': 'DEMO-SUP-003', 'kind': 'missing', 'record': rec('P-1', 'purchase'), 'differences': {}},
             {'supplier_ref': 'DEMO-SUP-003', 'kind': 'mismatch', 'record': rec('P-2', 'purchase', inv='INV-2'), 'differences': {'taxable_value': '-100.00'}}]
    [draft] = assist.supplier_followups(items, {'DEMO-SUP-003': 'Logistics Co'}, 'Client A', '2026-08')
    assert draft['invoices'] == 2 and draft['credit_at_risk'] == '180.00' and 'Logistics Co' in draft['message'] and 'INV-2' in draft['message']

@pytest.mark.parametrize('note,expected', [
    ('Rent to unregistered landlord: RCM ₹4,500 CGST monthly from Aug 2026', {'adjustment_type': 'rcm_liability', 'tax_head': 'cgst', 'amount': '4500.00', 'effective_from': '2026-08'}),
    ('Reverse ITC on exempt supplies IGST Rs. 1200.50 from 2026-09', {'adjustment_type': 'itc_reversal', 'tax_head': 'igst', 'amount': '1200.50', 'effective_from': '2026-09'}),
])
def test_rule_note_parsing(note, expected):
    parsed = assist.parse_rule_note(note)
    assert {k: parsed[k] for k in expected} == expected and parsed['missing'] == []

def test_rule_note_parsing_lists_what_is_missing():
    assert set(assist.parse_rule_note('Client pays some fees')['missing']) == {'adjustment_type', 'tax_head', 'amount', 'effective_from'}

def board_row(tone='done'):
    cell = {'tone': tone, 'label': 'Label', 'target': 'worksheet'}
    return {'period_id': 'p', 'period_code': '2026-08', 'client_name': 'Client A', 'sales': cell, 'purchases': cell, 'worksheet': cell}

def test_brief_is_built_only_from_board_and_audit():
    brief = assist.morning_brief([board_row('blocked'), board_row()], [{'action': 'tax_draft_approved'}], Decimal('180.00'))
    texts = ' '.join(b['text'] for b in brief)
    assert 'fix this first' in texts and '₹180.00' in texts and '1 approval(s)' in texts and '1 of 2 period(s) are complete' in texts
    assert all(b['href'].startswith('/') for b in brief)

def test_ask_explains_head_with_citations_and_abstains_otherwise():
    draft = {'id': 'abcdef123', 'state': 'approved', 'payload': {'worksheet': {'heads': {'cgst': dict(net='27.50', liability='117.50', output_tax='112.50', liability_adjustments='5.00', credit='90.00', itc_claimed='90.00', itc_reversal='0.00', other_credit='0.00')}},
             'inputs': {'output': [{'ref': 'SALE-1', 'cgst': '112.50'}], 'itc': [{'ref': 'RES-1', 'purchase_record_id': 'PUR-001', 'cgst': '90.00'}], 'adjustments': [{'ref': 'a1', 'type': 'rcm_liability', 'head': 'cgst', 'amount': '5.00', 'note': 'RCM'}]}}}
    out = assist.ask('Why is CGST net 27.50?', {'draft': draft})
    assert out['intent'] == 'explain_head' and 'CGST net is 27.50' in out['answer'] and len(out['citations']) == 3
    assert assist.ask('What is the GST rate on gold?', {})['intent'] is None

@pytest.mark.parametrize('question,intent', [('How much credit is at risk?', 'savings'), ('Why is CGST net 27.50?', 'explain_head'), ('What is blocking approval?', 'blockers'),
                                              ('What changed after approval?', 'changes'), ('Who approved this period?', 'who'), ('Which suppliers should we follow up?', 'suppliers')])
def test_ask_routes_each_suggested_question_to_its_own_intent(question, intent):
    assert assist.ask(question, {'events': [], 'blockers': [], 'savings': {'total': '0.00', 'items': []}, 'followups': []})['intent'] == intent
