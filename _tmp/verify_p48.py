"""Pass 48 verification."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('lead_engine').resolve()))
import lead_memory as lm

lm.MEMORY_FILE = pathlib.Path('lead_engine/data/_tmp_p48_verify.json')

row = {'business_name': 'Apex Plumbing', 'city': 'Rockford', 'website': 'apexplumbing.com'}

# 1. New EVT constants exist and are in _ALL_EVENT_TYPES
for const in ['EVT_APPROVED','EVT_UNAPPROVED','EVT_SCHEDULED','EVT_UNSCHEDULED']:
    val = getattr(lm, const)
    assert val in lm._ALL_EVENT_TYPES, f'{const} missing from _ALL_EVENT_TYPES'
    assert val in lm._EVENT_LABELS, f'{const} missing from _EVENT_LABELS'
print('PASS: all 4 new EVT constants registered with labels')

# 2. approved event does not change current_state
lm.record_suppression(row, 'contacted', note='initial')
lm.record_event(row, lm.EVT_APPROVED)
rec = lm.get_record(row)
assert rec['current_state'] == 'contacted', f'state changed unexpectedly: {rec["current_state"]}'
assert rec['history'][-1]['event_type'] == 'approved'
print('PASS: EVT_APPROVED recorded, current_state unchanged')

# 3. scheduled event with detail
lm.record_event(row, lm.EVT_SCHEDULED, detail='2026-03-19T07:30:00')
tl = lm.get_timeline(row)
sched = [e for e in tl if e.get('event_type') == 'scheduled']
assert len(sched) == 1
assert sched[0]['detail'] == '2026-03-19T07:30:00'
print('PASS: EVT_SCHEDULED recorded with detail')

# 4. unscheduled event
lm.record_event(row, lm.EVT_UNSCHEDULED)
tl2 = lm.get_timeline(row)
unsched = [e for e in tl2 if e.get('event_type') == 'unscheduled']
assert len(unsched) == 1
print('PASS: EVT_UNSCHEDULED recorded')

# 5. unapproved event
lm.record_event(row, lm.EVT_UNAPPROVED)
tl3 = lm.get_timeline(row)
unapp = [e for e in tl3 if e.get('event_type') == 'unapproved']
assert len(unapp) == 1
# Confirm ordering: contacted -> approved -> scheduled -> unscheduled -> unapproved
types = [e.get('event_type') or e.get('state') for e in tl3]
assert types == ['contacted', 'approved', 'scheduled', 'unscheduled', 'unapproved'], f'Wrong order: {types}'
print('PASS: full sequence in correct order')

# 6. Real memory file unchanged
lm.MEMORY_FILE = pathlib.Path('lead_engine/data/lead_memory.json')
real = lm.get_all_records()
contacted = [v for v in real.values() if v.get('current_state') == 'contacted']
assert len(contacted) == 34
print(f'PASS: real memory file intact ({len(contacted)} contacted records)')

pathlib.Path('lead_engine/data/_tmp_p48_verify.json').unlink(missing_ok=True)
print('\nAll 6 checks passed.')
