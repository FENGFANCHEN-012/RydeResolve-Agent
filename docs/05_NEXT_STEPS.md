# Next Steps — Remaining Work Before Submission

> **Last updated**: 2026-10-05. Submission deadline: **16 October 2026**; Demo Day: 3 November 2026.
> The earlier version of this list (2026-09-21) is in git history. Its items (debate engine, classifier,
> unit tests, multilingual notices, error handling) are done.

## Where the project stands

- The full pipeline runs end to end on `main` (PR #18): Collector → Classifier → Case Brief →
  Rider / Driver advocates + Policy → debate → Judge → Fairness → Executor or human review.
- Latest full evaluation (run 20261005-131434, D19): verdict **31/33 (93.9%)**, 0 failed runs,
  about 91 s and US$0.011 per case.
- 368 offline tests pass.

## P0 — required for scoring

| # | Task | Why | Owner | Status |
|---|------|-----|-------|--------|
| 1 | Submission draft: fill "business value" with the D19 numbers, close its open items | Judges read it first | billy | To do |
| 2 | CodeBuddy / WorkBuddy proof: add 1–2 screenshots of actual coding to `proof of usage of codebuddy/` | Hard rule: no proof, no scoring | team | 4 screenshots so far (research and introduction) |
| 3 | Sealed set: run `data/eval_cases/sealed` once, last, and report it as the generalisation number | The 33 dev / held-out cases have shaped the prompts (D16 / D18 overfitting note) | billy | Before 16 Oct |
| 4 | Blurb under 10 words and a 16:9 cover image (380 × 216) | Submission form | team | To do |

## Bonus

| # | Task | Notes |
|---|------|-------|
| 5 | Live demo URL | Tencent Lighthouse + Docker + Postgres (`STORE_URL`); update `docker-compose.yml` (it still lists ChromaDB and Redis) |
| 6 | Policy agent queries the Tencent ADP assistant | The ADP app is published over the same official files (`scripts/adp/`); compare it with our retriever in the eval |
| 7 | Demo video, 5–8 minutes (optional) | Show two dispute categories end to end and the live agent trace |
| 8 | Fraud and bad-faith agent | Design agreed in `09_FRAUD_AGENT_DESIGN.md`; the history store it needs exists; not built |

## Cleanup

| # | Task | Notes |
|---|------|-------|
| 9 | `src/core/confidence.py` `calculate_confidence()` is never called | Wire it in, or reword the Development Journal's Failure Case 1 |
| 10 | Reword `src/integrations/ryde_api.py` as a "simulated integration contract" | So nobody reads it as a live Ryde integration |
| 11 | Groq free tier rejects single requests over 8,000 tokens (some Judge prompts) | Only matters if Groq is the main provider; fallback covers it |
| 12 | Git history scrub (author email, co-author lines) | Parked; needs team agreement and a force-push |

## Not planned

- **Tencent Hunyuan as the agents' model**: TokenHub needs a paid inference service (402 on every
  model). The provider code stays (`LLM_PROVIDER=hunyuan`).
- **Gemini free tier as the main model**: 20 requests per day per model, about three cases.
- **Four-language UI, a PPT, a 3–5 minute video**: not in the competition brief
  (`01_PROJECT_REQUIREMENTS.md`). Party notices already support EN / ZH / MS / TA.
