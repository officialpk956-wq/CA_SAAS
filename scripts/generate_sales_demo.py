"""Generate only synthetic sales inputs; never import the engine or write its oracle."""
import argparse
import csv
from pathlib import Path

HEADERS = 'record_id document_type customer_type customer_ref invoice_number invoice_date supply_scope place_of_supply taxable_value cgst sgst igst cess invoice_total description'.split()

def rows():
    base = dict(zip(HEADERS, ['SALE-001','invoice','registered','DEMO-CUST-001','S-001','2026-08-01','domestic','DEMO-STATE-01','1000.00','90.00','90.00','0.00','0.00','1180.00','Synthetic domestic invoice']))
    changes = [
        {},
        dict(customer_type='unregistered', taxable_value='500.00', cgst='0.00', sgst='0.00', igst='90.00', invoice_total='590.00'),
        dict(taxable_value='250.00',cgst='22.50',sgst='22.50',invoice_total='295.00'),
        dict(taxable_value='0.00',cgst='0.00',sgst='0.00',invoice_total='0.00'),
        dict(invoice_number='DUP-001'), dict(invoice_number='DUP-001'),
        dict(invoice_date='31-08-2026'),dict(invoice_date='2026-07-31'),
        dict(taxable_value='oops'),dict(taxable_value='-1.00'),dict(taxable_value='1000.001'),
        dict(invoice_total='1000.00'),dict(customer_ref=''),dict(document_type='credit_note'),
        dict(supply_scope='export'),dict(record_id='SALE-DUP'),dict(record_id='SALE-DUP'),
        dict(place_of_supply=''),
        dict(taxable_value='0.00',cgst='0.00',sgst='0.00',invoice_total='0.00',description='=HYPERLINK("https://example.invalid","Synthetic text only")'),
    ]
    return [dict(base, **dict({'record_id':f'SALE-{i:03d}','invoice_number':f'S-{i:03d}'},**change)) for i,change in enumerate(changes,1)]

def generate(target, overwrite=False):
    target = Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w' if overwrite else 'x',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=HEADERS)
        writer.writeheader();writer.writerows(rows())

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    generate(Path(__file__).resolve().parents[1]/'sample_data/sales_v1/sales_register.csv', args.overwrite)
