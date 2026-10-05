"""Rule logic tests. All rates, fees and dates here are arbitrary test values, not statutory ones."""
from datetime import date
from decimal import Decimal
import pytest
from backend.gst_copilot import assist, rules

@pytest.mark.parametrize('invoice,day,month,expected', [
    (date(2026, 8, 10), 30, 11, date(2027, 11, 30)),   # FY 2026-27 ends 31 Mar 2027 -> next 30 Nov
    (date(2027, 3, 10), 30, 11, date(2027, 11, 30)),   # still FY 2026-27
    (date(2027, 4, 1), 30, 11, date(2028, 11, 30)),    # FY 2027-28
    (date(2026, 8, 10), 31, 3, date(2028, 3, 31)),     # (month, day) equal to FY end is not "after" it
])
def test_claim_deadline_is_first_occurrence_after_financial_year_end(invoice, day, month, expected):
    assert rules.claim_deadline(invoice, day, month) == expected

@pytest.mark.parametrize('period,due_day,expected', [('2026-08', 20, date(2026, 9, 20)), ('2026-12', 20, date(2027, 1, 20)), ('2027-01', 31, date(2027, 2, 28))])
def test_due_date_is_in_following_month_and_clamped(period, due_day, expected):
    assert rules.due_date(period, due_day) == expected

def test_estimates_round_half_up_and_respect_cap():
    assert rules.interest_estimate(Decimal('730.00'), Decimal('18'), 10) == Decimal('3.60')
    assert rules.interest_estimate(Decimal('730.00'), Decimal('18'), 0) == Decimal('0.00')
    assert rules.interest_estimate(Decimal('-5.00'), Decimal('18'), 10) == Decimal('0.00')
    assert rules.late_fee_estimate(10, Decimal('50'), Decimal('200')) == Decimal('200.00')
    assert rules.late_fee_estimate(3, Decimal('50'), Decimal('200')) == Decimal('150.00')

def test_legal_values_are_validated_and_normalised():
    assert rules.validate_legal_value('itc_claim_deadline', {'day': '30', 'month': 11, 'warn_days': 60}) == {'day': 30, 'month': 11, 'warn_days': 60}
    assert rules.validate_legal_value('blocked_credit_keywords', {'keywords': 'Motor Vehicle\n food \n\nfood'}) == {'keywords': ['food', 'motor vehicle']}
    assert rules.validate_legal_value('late_payment_interest', {'rate_percent': '18', 'due_day': 20}) == {'rate_percent': '18.00', 'due_day': 20}
    for key, bad in [('itc_claim_deadline', {'day': 31, 'month': 4, 'warn_days': 1}), ('itc_claim_deadline', {'day': 30, 'month': 11}),
                     ('late_fee', {'per_day': '-1', 'cap': '1', 'due_day': 20}), ('late_fee', {'per_day': '1', 'cap': '1', 'due_day': 20, 'x': 1}),
                     ('blocked_credit_keywords', {'keywords': ''}), ('nope', {})]:
        with pytest.raises(ValueError): rules.validate_legal_value(key, bad)

def test_blocked_keyword_is_case_insensitive():
    assert rules.blocked_keyword('Staff FOOD and beverages', ['food']) == 'food'
    assert rules.blocked_keyword('Printer paper', ['food']) is None

@pytest.mark.parametrize('frequency,start,end,period,expected', [
    ('monthly', '2026-08', None, '2026-07', False), ('monthly', '2026-08', None, '2027-02', True), ('monthly', '2026-08', '2026-10', '2026-11', False),
    ('quarterly', '2026-06', None, '2026-09', True), ('quarterly', '2026-06', None, '2026-08', False), ('quarterly', '2026-11', None, '2027-02', True),
    ('one_time', '2026-09', None, '2026-09', True), ('one_time', '2026-09', None, '2026-10', False),
])
def test_rule_applicability(frequency, start, end, period, expected):
    assert rules.rule_applies(frequency, start, end, period) is expected

@pytest.mark.parametrize('note,expected', [
    ('Confirm the client has paid cash before filing, from Aug 2026', {'rule_kind': 'reminder', 'effective_from': '2026-08', 'missing': []}),
    ('Quarterly RCM on legal fees Rs. 9,000.00 SGST from 2026-06 until Mar 2027', {'rule_kind': 'adjustment', 'frequency': 'quarterly', 'amount': '9000.00', 'effective_to': '2027-03'}),
    ('One-time ITC reversal IGST Rs. 500.00 only in Sep 2026', {'frequency': 'one_time', 'adjustment_type': 'itc_reversal', 'effective_from': '2026-09'}),
])
def test_note_parser_detects_kind_frequency_and_end(note, expected):
    parsed = assist.parse_rule_note(note)
    assert {k: parsed[k] for k in expected} == expected
