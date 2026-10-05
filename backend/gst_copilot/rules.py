"""Rule logic that depends on law or on a firm's own practice. Pure functions, no database.

Statutory values are NEVER hard-coded here. The firm's CA enters each value with a source reference and
confirms it; until then the related check does not run. Estimates are labelled as estimates.
"""
import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

LEGAL_TEMPLATES = {
    'itc_claim_deadline': {
        'title': 'ITC claim deadline',
        'help': 'The last day and month, after a financial year (April–March) ends, by which input tax credit for that year can be claimed. Warn this many days before it.',
        'fields': {'day': 'int', 'month': 'int', 'warn_days': 'int'},
    },
    'blocked_credit_keywords': {
        'title': 'Blocked-credit descriptions',
        'help': 'Words that, when found in a purchase description, mean the firm treats the credit as blocked or needing review. One per line.',
        'fields': {'keywords': 'list'},
    },
    'late_payment_interest': {
        'title': 'Interest on late payment',
        'help': 'Annual interest rate on tax paid late, and the day of the following month by which it is due.',
        'fields': {'rate_percent': 'decimal', 'due_day': 'int'},
    },
    'late_fee': {
        'title': 'Late fee for a late return',
        'help': 'Late fee per day, the maximum, and the day of the following month by which the return is due.',
        'fields': {'per_day': 'decimal', 'cap': 'decimal', 'due_day': 'int'},
    },
    'return_due_dates': {
        'title': 'Return due dates',
        'help': 'Day of the month after the period by which each return is due, for monthly filers. Shown on the Board once confirmed.',
        'fields': {'gstr1_day': 'int', 'gstr3b_day': 'int'},
    },
    'credit_utilisation_order': {
        'title': 'Credit utilisation order (set-off)',
        'help': 'The order in which credit is used against liability, one step per line as CREDIT>LIABILITY (e.g. IGST>IGST). '
                'Steps run top to bottom; a pair that is not listed is never used. Until this is confirmed, set-off and cash payable are not computed.',
        'fields': {'steps': 'steps'},
    },
    'payment_rounding': {
        'title': 'Rounding of cash payable',
        'help': 'Round each head’s cash payable to a multiple of this amount (1.00 = whole rupees; 0.01 = no rounding), in this direction.',
        'fields': {'multiple': 'decimal', 'direction': 'choice'},
        'options': {'direction': ['half_up', 'up', 'down']},
    },
}
LIMITS = {'day': (1, 31), 'month': (1, 12), 'warn_days': (0, 730), 'due_day': (1, 31), 'gstr1_day': (1, 31), 'gstr3b_day': (1, 31)}

def due_status(due: date, today: date, done: bool, done_word: str = 'done') -> dict:
    """Board chip for a return deadline: done once handled; otherwise by days left."""
    days = (due - today).days
    if done: tone, label = 'done', f'Due {due.strftime("%d %b")} · {done_word}'
    elif days < 0: tone, label = 'blocked', f'Overdue by {-days} day(s) ({due.strftime("%d %b")})'
    elif days <= 3: tone, label = 'action', f'Due {due.strftime("%d %b")} · {days} day(s) left'
    else: tone, label = 'waiting', f'Due {due.strftime("%d %b")} · {days} days left'
    return {'date': due.isoformat(), 'days_left': days, 'tone': tone, 'label': label}
CENT = Decimal('0.01')

def validate_legal_value(key, value):
    """Normalise a CA-entered value for a template. Raises ValueError with a readable message."""
    if key not in LEGAL_TEMPLATES: raise ValueError(f'Unknown legal rule {key!r}')
    if not isinstance(value, dict): raise ValueError('Value must be an object')
    fields = LEGAL_TEMPLATES[key]['fields']
    extra = set(value) - set(fields)
    if extra: raise ValueError(f'Unexpected fields: {sorted(extra)}')
    out = {}
    for name, kind in fields.items():
        raw = value.get(name)
        if raw in (None, '', []): raise ValueError(f'{name} is required')
        if kind == 'int':
            try: n = int(str(raw))
            except ValueError: raise ValueError(f'{name} must be a whole number')
            lo, hi = LIMITS[name]
            if not lo <= n <= hi: raise ValueError(f'{name} must be between {lo} and {hi}')
            out[name] = n
        elif kind == 'decimal':
            try: d = Decimal(str(raw))
            except InvalidOperation: raise ValueError(f'{name} must be a number')
            if not d.is_finite() or d < 0 or d > Decimal('1000000'): raise ValueError(f'{name} must be between 0 and 1,000,000')
            out[name] = format(d.quantize(CENT, ROUND_HALF_UP), '.2f')
        elif kind == 'steps':
            from .setoff import parse_steps
            items = raw if isinstance(raw, list) else str(raw).splitlines()
            out[name] = [f'{c.upper()}>{l.upper()}' for c, l in parse_steps(items)]
        elif kind == 'choice':
            options = LEGAL_TEMPLATES[key]['options'][name]
            if raw not in options: raise ValueError(f'{name} must be one of: {", ".join(options)}')
            out[name] = raw
        else:
            items = raw if isinstance(raw, list) else str(raw).splitlines()
            words = sorted({w.strip().lower() for w in items if w.strip()})
            if not words: raise ValueError(f'{name} needs at least one entry')
            if any(len(w) > 60 for w in words): raise ValueError('Each keyword must be 60 characters or fewer')
            out[name] = words
    if key == 'itc_claim_deadline':
        try: date(2001, out['month'], out['day'])  # non-leap year: rejects 31 Apr, 30 Feb, 29 Feb
        except ValueError: raise ValueError('That day does not exist in that month')
    if key == 'payment_rounding' and Decimal(out['multiple']) <= 0:
        raise ValueError('multiple must be greater than 0 (use 0.01 for no rounding)')
    return out

def fy_end(d: date) -> date:
    """Indian financial year runs April–March."""
    return date(d.year + (1 if d.month >= 4 else 0), 3, 31)

def claim_deadline(invoice_date: date, day: int, month: int) -> date:
    """First occurrence of (month, day) after the financial year of the invoice ends."""
    end = fy_end(invoice_date)
    candidate = date(end.year, month, day)
    return candidate if candidate > end else date(end.year + 1, month, day)

def due_date(period_code: str, due_day: int) -> date:
    """due_day of the month after the period, clamped to that month's length."""
    y, m = map(int, period_code.split('-'))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return date(y, m, min(due_day, calendar.monthrange(y, m)[1]))

def interest_estimate(amount: Decimal, rate_percent: Decimal, days_late: int) -> Decimal:
    """Simple interest, rounded half-up to paise. An estimate: it ignores credit ledgers and set-off."""
    if amount <= 0 or days_late <= 0: return Decimal('0.00')
    return (amount * Decimal(rate_percent) / 100 * days_late / 365).quantize(CENT, ROUND_HALF_UP)

def late_fee_estimate(days_late: int, per_day: Decimal, cap: Decimal) -> Decimal:
    if days_late <= 0: return Decimal('0.00')
    return min(Decimal(per_day) * days_late, Decimal(cap)).quantize(CENT, ROUND_HALF_UP)

def blocked_keyword(description: str, keywords) -> str | None:
    text = (description or '').lower()
    return next((k for k in keywords if k in text), None)

# --- Knowledge-rule applicability --------------------------------------------------------------

FREQUENCIES = ('monthly', 'quarterly', 'one_time')

def _months(period_code: str) -> int:
    y, m = map(int, period_code.split('-')); return y * 12 + (m - 1)

def rule_applies(frequency: str, effective_from: str, effective_to: str | None, period_code: str) -> bool:
    """monthly: every month from the start (to the optional end); quarterly: every third month from the
    start; one_time: only the start month."""
    if not effective_from or period_code < effective_from: return False
    if effective_to and period_code > effective_to: return False
    if frequency == 'one_time': return period_code == effective_from
    if frequency == 'quarterly': return (_months(period_code) - _months(effective_from)) % 3 == 0
    return True
