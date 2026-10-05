import csv
import io
import json
from pathlib import Path
import pytest
from backend.gst_copilot.sales import parse_sales, summarize, MAX_BYTES
from backend.gst_copilot.services.export_service import sanitize_value
from scripts.generate_sales_demo import generate

SAMPLE = Path('sample_data/sales_v1/sales_register.csv')

def changed(**fields):
    reader=csv.DictReader(io.StringIO(SAMPLE.read_text(encoding='utf-8')))
    row=next(reader);row.update(fields)
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=reader.fieldnames);writer.writeheader();writer.writerow(row)
    return stream.getvalue().encode()

def test_independent_sales_oracle_and_accounting():
    rows=parse_sales(SAMPLE.read_bytes(),'2026-08')
    oracle=json.loads(Path('tests/fixtures/sales_v1/expected_results.json').read_text())
    assert [{'row_number':r['row_number'],'status':r['validation_status'],'issues':r['issues']} for r in rows] == oracle
    expected=json.loads(Path('tests/fixtures/sales_v1/expected_summary.json').read_text())
    summary=summarize(rows)
    assert {k:summary[k] for k in ('source_rows','ready','duplicate','invalid','unsupported')} == {k:expected[k] for k in ('source_rows','ready','duplicate','invalid','unsupported')}
    assert summary['pending'] == 19 and summary['included'] == 0
    for row in rows: row['decision']='reviewed' if row['validation_status']=='ready' else 'excluded'
    result=summarize(rows)
    assert result['included_totals']==expected['reviewed_totals']
    assert result['included']==5 and result['excluded']==14 and result['pending']==0
    assert result['source_rows']==result['included']+result['excluded']+result['pending']

def test_generator_preserves_oracle_and_existing_input(tmp_path):
    target=tmp_path/'demo.csv';generate(target)
    assert target.read_bytes()==SAMPLE.read_bytes()
    with pytest.raises(FileExistsError): generate(target)
    generate(target,overwrite=True)
    assert target.read_bytes()==SAMPLE.read_bytes()

@pytest.mark.parametrize('payload',[b'',b'wrong,header\n1,2',b'a,a\n1,2',b'\xff',b'\x00',b'x'*(MAX_BYTES+1)], ids=['empty','headers','duplicate-headers','encoding','control','oversized'])
def test_malformed_sales_file_rejected(payload):
    with pytest.raises(ValueError): parse_sales(payload,'2026-08')

@pytest.mark.parametrize('changes,issue',[
    ({'invoice_date':'2026-02-30'},'invalid_date'),({'invoice_date':'2026-8-01'},'invalid_date'),
    ({'customer_type':'unknown'},'invalid_customer_type'),({'customer_ref':'REAL-CLIENT'},'invalid_customer_ref'),
    ({'record_id':''},'missing_record_id'),({'invoice_number':''},'missing_invoice_number'),
    ({'invoice_number':' S-001'},'whitespace_invoice_number'),({'cgst':'NaN'},'invalid_cgst'),
    ({'cgst':'90.000'},'invalid_cgst'),({'cgst':'1000000000000.00'},'invalid_cgst'),
    ({'cgst':'1e2'},'invalid_cgst'),({'cgst':''},'invalid_cgst'),
])
def test_sales_field_validation(changes,issue):
    assert issue in parse_sales(changed(**changes),'2026-08')[0]['issues']

def test_bom_and_reordered_headers():
    assert parse_sales(b'\xef\xbb\xbf'+changed(),'2026-08')[0]['validation_status']=='ready'
    reader=csv.DictReader(io.StringIO(changed().decode()));row=next(reader)
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(reversed(reader.fieldnames)));writer.writeheader();writer.writerow(row)
    assert parse_sales(stream.getvalue().encode(),'2026-08')[0]['raw_data']==row

def test_csv_shape_limits_and_quote_errors():
    header=changed().splitlines()[0]
    for content in (header+b'\n',changed()+b'a,b\n',header+b'\n"unclosed',changed(description='x'*2001)):
        with pytest.raises(ValueError): parse_sales(content,'2026-08')
    row=changed().splitlines()[1]
    with pytest.raises(ValueError,match='10000'): parse_sales(header+b'\n'+(row+b'\n')*10001,'2026-08')

def test_invalid_duplicate_counterpart_is_fenced():
    header,row=changed().splitlines()
    other=changed(record_id='ANOTHER',taxable_value='oops').splitlines()[1]
    rows=parse_sales(header+b'\n'+row+b'\n'+other+b'\n','2026-08')
    assert all(r['validation_status']=='duplicate' for r in rows)
    assert 'invalid_taxable_value' in rows[1]['issues']

def test_export_text_is_safe_and_visible():
    assert sanitize_value('=SUM(A1)')=="'=SUM(A1)"
    assert sanitize_value('note\x01end')==r'note\u0001end'
