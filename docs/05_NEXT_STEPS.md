# Next Steps — Remaining Work Before Submission

> **Last updated**: 2026-10-07. Submission deadline: **16 October 2026**; Demo Day: 3 November 2026.
> The earlier version of this list (2026-09-21) is in git history. Its items (debate engine, classifier,
> unit tests, multilingual notices, error handling) are done.

## Where the project stands

- Main includes the D22 safety/history changes (PR #22). The pipeline now includes Fraud.
- Latest full evaluation is D20: **35/37 (94.6%)**, refund 27/29. It resumed 14 cases after
  daily quota reset; both wrong no-show proposals were routed to human review.
- D21 and D22 checks were targeted, not a full re-evaluation of the latest code.
- Local fixes on `fix/demo-reliability` address selection races, stream failure/completion,
  retry recovery, HTML escaping, uploads, access control, readiness and deployment isolation.
- Shared Postgres still times out on this machine. `.env.local` selects independent SQLite
  records and the existing official Qdrant collection (165 chunks, bge-base 768 dimensions).
  Shared history has not been imported.
- Offline regression: 418 backend tests and 21 frontend tests pass. Groq live smoke found a
  request-size limit with 3 rounds (8,927 tokens vs 8,000 allowed), so the local demo uses the
  project's default 1 round. Re-check the chosen provider/configuration before the demo;
  this configuration does not inherit the D20 evaluation accuracy.

## P0 — required for scoring

| # | Task | Why | Owner | Status |
|---|------|-----|-------|--------|
| 1 | Submission draft: fill "business value" with the D20 numbers and D21/D22 limitations, close its open items | Judges read it first | billy | To do |
| 2 | CodeBuddy / WorkBuddy proof: add 1–2 screenshots of actual coding to `proof of usage of codebuddy/` | Hard rule: no proof, no scoring | team | 4 screenshots so far (research and introduction) |
| 3 | Sealed set: run `data/eval_cases/sealed` once, last, and report it as the generalisation number | The labelled dev / held-out cases have shaped the prompts (D16 / D18 overfitting note) | billy | Before 16 Oct |
| 4 | Blurb under 10 words and a 16:9 cover image (380 × 216) | Submission form | team | To do |

## Bonus

| # | Task | Notes |
|---|------|-------|
| 5 | Live demo URL | Tencent Lighthouse + Docker + Postgres (`STORE_URL`); compose now passes runtime .env and excludes secrets from images; clean build and HTTPS deployment still need validation |
| 6 | Policy agent queries the Tencent ADP assistant | The ADP app is published over the same official files (`scripts/adp/`); compare it with our retriever in the eval |
| 7 | Demo video, 5–8 minutes (optional) | Show two dispute categories end to end and the live agent trace |
| 8 | Fraud and bad-faith agent | Implemented in D20, refined in D21/D22; keep submission description current |

## Cleanup

| # | Task | Notes |
|---|------|-------|
| 9 | `src/core/confidence.py` `calculate_confidence()` is never called | Wire it in, or reword the Development Journal's Failure Case 1 |
| 10 | Reword `src/integrations/ryde_api.py` as a "simulated integration contract" | So nobody reads it as a live Ryde integration |
| 11 | Groq free tier rejects single requests over 8,000 tokens (some Judge prompts) | Live-check the actual Groq quota; fallback is opt-in and never overrides budget/auth/config failures |
| 12 | Git history scrub (author email, co-author lines) | Parked; needs team agreement and a force-push |

## Not planned

- **Tencent Hunyuan as the agents' model**: TokenHub needs a paid inference service (402 on every
  model). The provider code stays (`LLM_PROVIDER=hunyuan`).
- **Gemini free tier as the main model**: 20 requests per day per model, about three cases.
- **Four-language UI, a PPT, a 3–5 minute video**: not in the competition brief
  (`01_PROJECT_REQUIREMENTS.md`). Party notices already support EN / ZH / MS / TA.
