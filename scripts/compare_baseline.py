import csv
from pathlib import Path

def load(ts):
    p = Path(f'data/eval/{ts}/results.csv')
    return {r['dispute_id']: {'actual': r['actual_verdict'], 'expected': r['expected_verdict'], 'ok': r['verdict_ok']=='True'}
            for r in csv.DictReader(p.read_text().splitlines())}

clean1 = load('20261007-101918')
clean2 = load('20261007-102733')
safe1  = load('20261006-225718')
safe2  = load('20261006-230550')

all_clean = {**clean1, **clean2}
all_safe  = {**safe1, **safe2}

print('=== Original Sealed Cases: Clean Main vs Safe Optimizations ===')
print('Case     Expected         Clean        Safe')
print('-'*50)

for case in sorted(all_clean.keys()):
    c = all_clean[case]
    s = all_safe.get(case, {})
    c_mark = f"{c['actual']:<12}{'OK' if c['ok'] else 'X'}"
    s_mark = f"{s.get('actual','N/A'):<12}{'OK' if s.get('ok') else 'X' if s else '-'}"
    print(f"{case:<8} {c['expected']:<16} {c_mark:<14} {s_mark}")

c_ok = sum(1 for v in all_clean.values() if v['ok'])
s_ok = sum(1 for v in all_safe.values() if v.get('ok'))
print(f"\nClean main:  {c_ok}/{len(all_clean)} = {c_ok/len(all_clean):.0%}")
print(f"Safe opts:   {s_ok}/{len(all_safe)} = {s_ok/len(all_safe):.0%}")

improved = sum(1 for k in all_clean if not all_clean[k]['ok'] and all_safe.get(k,{}).get('ok'))
worsened = sum(1 for k in all_clean if all_clean[k]['ok'] and not all_safe.get(k,{}).get('ok'))
print(f"\nSafe opts improved: {improved} cases")
print(f"Safe opts worsened: {worsened} cases")
