import csv
from pathlib import Path

def load_run(ts):
    p = Path(f'data/eval/{ts}/results.csv')
    if not p.exists():
        return {}
    rows = list(csv.DictReader(p.read_text().splitlines()))
    return {r['dispute_id']: {
        'actual': r['actual_verdict'],
        'expected': r['expected_verdict'],
        'ok': r['verdict_ok'] == 'True',
        'tokens': int(r['prompt_tokens']),
    } for r in rows}

runs = {
    'baseline_5new': '20261006-210212',
    'safeopts_5new': '20261006-224441',
    'safeopts_all14': '20261007-092722',
}

data = {k: load_run(v) for k, v in runs.items()}

print("=== Case-by-case comparison ===\n")
print(f"{'Case':<10} {'Baseline':<15} {'SafeOpts_5':<15} {'SafeOpts_14':<15} {'Expected':<15}")
print("-" * 70)

all_cases = sorted(set(data['safeopts_all14'].keys()))
for case in all_cases:
    b = data['baseline_5new'].get(case, {})
    s5 = data['safeopts_5new'].get(case, {})
    s14 = data['safeopts_all14'].get(case, {})

    b_v = f"{b.get('actual','N/A')}{' OK' if b.get('ok') else ' X' if b else ' -'}"
    s5_v = f"{s5.get('actual','N/A')}{' OK' if s5.get('ok') else ' X' if s5 else ' -'}"
    s14_v = f"{s14.get('actual','N/A')}{' OK' if s14.get('ok') else ' X' if s14 else ' -'}"
    exp = s14.get('expected', s5.get('expected', b.get('expected', 'N/A')))

    print(f"{case:<10} {b_v:<15} {s5_v:<15} {s14_v:<15} {exp:<15}")

print("\n=== Summary ===")
for name, d in data.items():
    ok = sum(1 for v in d.values() if v['ok'])
    total = len(d)
    tokens = sum(v['tokens'] for v in d.values())
    print(f"{name}: {ok}/{total} = {ok/total:.0%} | tokens={tokens:,}")
