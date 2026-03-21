import csv, sys
from pathlib import Path

LEAD_ENGINE = Path(__file__).resolve().parent.parent / 'lead_engine'
sys.path.insert(0, str(LEAD_ENGINE))

from send.email_sender_agent import is_real_send

queue_csv = LEAD_ENGINE / 'queue' / 'pending_emails.csv'
rows = list(csv.DictReader(open(queue_csv, encoding='utf-8')))

real_sent   = [r for r in rows if is_real_send(r)]
sent_at_set = [r for r in rows if (r.get('sent_at') or '').strip()]
has_mid     = [r for r in rows if (r.get('message_id') or '').strip()]

print(f'Total rows     : {len(rows)}')
print(f'is_real_send   : {len(real_sent)}')
print(f'has sent_at    : {len(sent_at_set)}')
print(f'has message_id : {len(has_mid)}')
print()
print('Sample real-sent rows (first 5):')
for r in real_sent[:5]:
    biz = r.get('business_name','')[:40]
    web = (r.get('website') or '')[:35]
    ph  = (r.get('phone') or '')
    ct  = (r.get('sent_at') or '')[:19]
    print(f'  [{ct}] {biz:<40s} web={web:<35s} ph={ph}')

print()
print('Identity coverage of real-sent rows:')
has_web  = sum(1 for r in real_sent if (r.get('website') or '').strip())
has_ph   = sum(1 for r in real_sent if (r.get('phone') or '').strip())
print(f'  has website  : {has_web}/{len(real_sent)}')
print(f'  has phone    : {has_ph}/{len(real_sent)}')
