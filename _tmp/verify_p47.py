"""Pass 47 verification."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('lead_engine').resolve()))
import lead_memory as lm

# Use throwaway test file
lm.MEMORY_FILE = pathlib.Path('lead_engine/data/_tmp_p47_verify.json')

row = {'business_name': 'Test Plumbing', 'city': 'Rockford', 'website': 'testplumbing.com'}

# 1. record_event appends without changing current_state
lm.record_suppression(row, 'contacted', note='initial contact')
lm.record_event(row, lm.EVT_OBSERVATION_ADDED, detail='saw their trucks had no signage')
rec = lm.get_record(row)
assert rec['current_state'] == 'contacted', 'state should still be contacted'
assert len(rec['history']) == 2
assert rec['history'][1]['type'] == 'event'
assert rec['history'][1]['event_type'] == lm.EVT_OBSERVATION_ADDED
print('PASS: record_event appends without changing current_state')

# 2. record_event creates record if none exists
row2 = {'business_name': 'New HVAC', 'city': 'Chicago', 'website': 'newhvac.com'}
lm.record_event(row2, lm.EVT_DRAFTED, detail='v9 draft created')
rec2 = lm.get_record(row2)
assert rec2 is not None
assert 'current_state' not in rec2 or rec2.get('current_state') is None
assert not lm.is_suppressed(row2), 'event-only record should not be suppressed'
print('PASS: event-only record created, is_suppressed=False')

# 3. get_timeline returns sorted oldest-first, back-fills type+label
lm.record_event(row, lm.EVT_DRAFT_REGENERATED, detail='regenerated after obs')
lm.record_suppression(row, 'revived', note='operator revived')
lm.record_event(row, lm.EVT_REPLIED, detail='channel=email')
timeline = lm.get_timeline(row)
assert len(timeline) == 5
assert all('type' in e for e in timeline), 'all entries must have type'
assert all('label' in e for e in timeline), 'all entries must have label'
# Confirm ordering is oldest-first
ts_list = [e['ts'] for e in timeline]
assert ts_list == sorted(ts_list), 'timeline must be sorted oldest-first'
print(f'PASS: get_timeline returns {len(timeline)} entries sorted oldest-first, all have type+label')

# 4. State transitions back-fill correctly (pre-P47 shape has no 'type')
# Simulate a legacy entry by manually inserting one without 'type'
rec = lm.get_record(row)
legacy_entry = {'state': 'hold', 'ts': '2026-01-01T00:00:00Z', 'note': 'legacy'}
rec['history'].insert(0, legacy_entry)
from lead_memory import _save, _load
data = _load()
data[lm.lead_key(row)] = rec
_save(data)
timeline2 = lm.get_timeline(row)
first = timeline2[0]
assert first['type'] == 'state', 'legacy entry back-filled as state'
assert first['label'] == 'Put on hold', f'unexpected label: {first["label"]}'
print('PASS: legacy history entries back-filled with type=state and correct label')

# 5. All EVT_* constants are in _ALL_EVENT_TYPES
for attr in ['EVT_DRAFTED','EVT_OBSERVATION_ADDED','EVT_DRAFT_REGENERATED',
             'EVT_REPLIED','EVT_NOTE_ADDED','EVT_FOLLOWUP_SENT']:
    val = getattr(lm, attr)
    assert val in lm._ALL_EVENT_TYPES, f'{attr} missing from _ALL_EVENT_TYPES'
print('PASS: all EVT_* constants registered in _ALL_EVENT_TYPES')

# 6. Real memory file integrity unchanged (34 contacted records still present)
lm.MEMORY_FILE = pathlib.Path('lead_engine/data/lead_memory.json')
real = lm.get_all_records()
contacted = [v for v in real.values() if v.get('current_state') == 'contacted']
assert len(contacted) == 34, f'Expected 34 contacted, got {len(contacted)}'
print(f'PASS: real lead_memory.json still has {len(contacted)} contacted records untouched')

# Cleanup
pathlib.Path('lead_engine/data/_tmp_p47_verify.json').unlink(missing_ok=True)
print()
print('All 6 checks passed.')
