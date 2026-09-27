# Evaluation Baseline — Run 20260925-144037

First scored run of the full pipeline, used as the reference point for every later
fix. Plan and metric definitions: [06_EVAL_PLAN.md](06_EVAL_PLAN.md).
Raw traces and the HTML report are local only (`data/eval/` is gitignored).

## Setup

| Item | Value |
|---|---|
| Cases | 13 mock disputes (`data/mock_disputes/*.json`), 8 dispute types, each with an answer key |
| Runner | `python scripts/eval.py` (1 repeat per case) |
| Model | `openai/gpt-oss-120b` on Groq free tier (200k tokens/day, 8k tokens/min) |
| Debate | `MAX_DEBATE_ROUNDS=3` |
| Retrieval | Qdrant Cloud, dense (bge-small) + BM25 hybrid with RRF, 108 chunks from 11 policy docs |
| Dates | 9 cases on 2026-09-25; 4 cases (NS-003, RD-001, RD-002, SQ-001) re-run on 2026-09-27 after the first attempt hit the Groq daily limit |

Note: the Collector's deterministic tools (work in progress, not yet merged) were
active in the local build used for this run.

## Headline results

| Metric | Target | Result |
|---|---|---|
| End-to-end verdict accuracy | ≥ 0.85 | **0.23** (3/13) FAIL |
| Arbitrator's own ruling, before escalation gates | — | 0.70 (7/10 that produced a real ruling) |
| Refund accuracy | ≥ 0.85 | 0.11 (1/9) FAIL |
| Classification accuracy | ≥ 0.90 | 1.00 (11/11) PASS |
| P0 safety escalation recall | 1.00 | 1.00 (1/1) PASS |
| Missing-data escalation | 1.00 | 1.00 (2/2) PASS |
| Retrieval Hit@3 | ≥ 0.90 | 1.00 (13/13 offline, 12/12 live) PASS |
| Citation validity | ≥ 0.95 | 1.00 (22/22) PASS |
| Failure (crash) rate | ≤ 0.02 | 0.00 PASS |
| Latency p50 / p95 | — | 170 s / 199 s (74% is rate-limit waiting) |
| Tokens | — | ~21k per case, 272k total, 128 LLM calls |

## Per-case results

| Case | Expected | Arbitrator ruling (conf.) | Final | OK | Main reason |
|---|---|---|---|---|---|
| CF-001 | upheld | upheld (0.93) | escalated | ✗ | Case-policy citation stripped as unverified → forced review (F1) |
| CR-001 | upheld | upheld (0.95) | escalated | ✗ | Citation stripped (F1) |
| CR-002 | dismissed | upheld (0.93) | escalated | ✗ | Passenger agent `json_validate_failed` → evidence-only fallback → wrong ruling; Fairness caught it (F4) |
| DR-001 | upheld | upheld (0.95) | escalated | ✗ | Fairness false `internal_inconsistency`: evidence not visible to the check (F2) |
| FD-001 | upheld | partially_upheld (0.92) | escalated | ✗ | Citation stripped (F1) + Fairness false alarm (F2) |
| FD-002 | dismissed | dismissed (0.96) | escalated | ✗ | Citation stripped (F1) |
| NS-001 | upheld | upheld (0.96) | escalated | ✗ | 3 citations stripped (F1) |
| NS-002 | dismissed | fallback (0.00) | escalated | ✗ | Arbitrator prompt ~8.1k tokens > 8k TPM → HTTP 413 (F3) |
| NS-003 | must escalate | fallback (0.00) | escalated | ✓ | Missing evidence; Arbitrator also hit `json_validate_failed` |
| RD-001 | upheld | upheld (0.78) | escalated | ✗ | Arbitrator flagged a policy conflict; compliance flags contradicted its verdict (genuine catch) |
| RD-002 | dismissed | dismissed (0.95) | resolved | ✓ | — |
| SI-001 | must escalate | not reached | escalated | ✓ | P0 safety, escalated by the Classifier (by design) |
| SQ-001 | partially_upheld | upheld (0.93) | escalated | ✗ | Arbitrator over-ruled with two different speed limits; Fairness caught it (genuine catch) |

## Findings

The reasoning core is mostly right; the escalation gates are the bottleneck.
8 of the 10 wrong outcomes come from false alarms or infrastructure limits, not
from genuine doubt about the ruling.

| # | Problem | Cases | Planned fix |
|---|---|---|---|
| F1 | Arbitrator strips citations to rules that come with the case (`platform_policy.*`, `cancellation_policy.*`) because they are not in the RAG whitelist, then forces human review | CF-001, CR-001, FD-001, FD-002, NS-001 | Accept references that exist in the case's own policy keys |
| F2 | Fairness semantic check sees only shortened advocate summaries, not case evidence → false inconsistencies | DR-001, FD-001 | Give the check the case evidence / Collector findings (Fairness owner) |
| F3 | 3 debate rounds push the Arbitrator request over Groq's 8k TPM | NS-002 | `MAX_DEBATE_ROUNDS=1` |
| F4 | Groq `json_validate_failed` falls straight back to a degraded answer | CR-002, NS-003 | Retry once before falling back |
| F5 | Daily quota exhaustion looked like an ordinary escalation | 4 runs on 2026-09-25 | Done: debate stops on quota exhaustion (#14); eval quarantines and resumes affected runs |

RD-001 and SQ-001 are correct escalations: the Arbitrator's reasoning was
internally inconsistent and the Fairness layer caught it. Arbitrator reasoning
quality is the next thing to watch once F1–F4 are fixed.

## Next

Apply F1, F3 and F4, re-run the same 13 cases, and compare against this baseline.
