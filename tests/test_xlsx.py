"""Excel upload conversion: an Excel copy of the synthetic purchase register must validate exactly like the CSV."""
import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.gst_copilot.parser import parse_purchases, parse_suppliers
from backend.gst_copilot.validation import validate_row
from backend.gst_copilot.xlsx import is_xlsx, to_csv

DATA = Path(__file__).resolve().parents[1] / 'sample_data/v1'
AMOUNTS = {'taxable_value', 'cgst', 'sgst', 'igst', 'cess', 'invoice_total'}


def workbook(rows) -> bytes:
    book = Workbook(); sheet = book.active
    for row in rows: sheet.append(row)
    out = BytesIO(); book.save(out); return out.getvalue()


def typed(header, row):
    """What a person typing the register into Excel gets: real numbers and real dates."""
    def one(h, v):
        try: return float(v) if h in AMOUNTS else date.fromisoformat(v) if h == 'invoice_date' else v
        except ValueError: return v  # deliberately bad cells stay text, as Excel would keep them
    return [one(h, v) for h, v in zip(header, row)]


def outcome(path, suppliers):
    return [repr(validate_row(r, suppliers)).replace(repr(path.name), 'FILE') for r in parse_purchases(str(path))]


def test_excel_register_validates_like_csv(tmp_path):
    text = (DATA / 'purchase_register.csv').read_text(encoding='utf-8-sig')
    rows = list(csv.reader(StringIO(text)))
    content = workbook([rows[0]] + [typed(rows[0], r) for r in rows[1:]] + [[None] * len(rows[0])])
    assert is_xlsx(content)
    converted = list(csv.DictReader(StringIO(to_csv(content).decode())))
    original = list(csv.DictReader(StringIO(text)))
    assert len(converted) == len(original)  # the blank trailing row is dropped
    for a, b in zip(converted, original):
        assert a.keys() == b.keys()
        for k in a:
            same = a[k] == b[k]
            if not same and k in AMOUNTS: same = Decimal(a[k]) == Decimal(b[k])
            assert same, (k, a[k], b[k])
    suppliers = parse_suppliers(DATA / 'suppliers.csv')
    (tmp_path / 'x.csv').write_bytes(to_csv(content))
    assert outcome(tmp_path / 'x.csv', suppliers) == outcome(DATA / 'purchase_register.csv', suppliers)


def test_conversion_does_not_hide_bad_amounts():
    content = workbook([['cgst', 'sgst', 'invoice_number'], [1234.5, 10.125, 7]])
    assert to_csv(content).decode().splitlines()[1] == '1234.50,10.125,7'  # three decimals pass through; validation rejects them


def test_not_excel():
    assert not is_xlsx(b'record_id,x\n1,2\n')
    with pytest.raises(ValueError): to_csv(b'PK\x03\x04 not really a workbook')
