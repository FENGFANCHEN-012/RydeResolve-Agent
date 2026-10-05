# Fraud & Bad-Faith Detection Agent — Design (2026-10-02, not yet built)

Stretch goal from the handbook (p.24): an agent that runs in parallel, flags dispute abuse,
fake claims and collusion, and feeds risk signals to the Judge. This document fixes the design
before any code is written. Status: **agreed, awaiting implementation.**

## 1. Principles (agreed in review)

1. **Code scores, the LLM only reads chat.** Every risk score comes from deterministic rules
   over structured data, so the same inputs always give the same score and a reviewer can see
   which rule added what. The one LLM call (optional, only when chat logs exist) classifies
   chat semantics into a fixed label set; it never assigns scores.
2. **Risk signals inform, they never convict.** No verdict may rest on risk alone. High risk
   routes to a person with a full report; it never auto-dismisses a complaint.
3. **Restrictions are human decisions.** The system never blocks a user from filing disputes.
   A human reviewer may impose limits (no auto-refund, all disputes manually reviewed) after
   confirming fraud; every restriction is audit-logged, disclosed to the user, appealable and
   time-bound. Auto-banning was proposed and rejected: a wrongly-blocked genuine victim is the
   worst failure the system can produce, and the loop (flagged -> dismissed -> more flagged)
   self-reinforces.
4. **Only human-confirmed flags enter history.** The agent's own suspicions are stored as
   `pending` and excluded from scoring, same pattern as D8 precedents. AI suspicion must not
   pollute the record it scores against.

## 2. Position in the pipeline

Runs **after Case Brief, in parallel with the debate** (it needs no LLM for scoring, so it
costs no Cerebras calls on that path). Its report goes to the **Judge and Fairness only**:

- The advocates do not see it. They have already received the brief when it runs, and an
  advocate must not argue from the other party's record ("he has priors") instead of the case.
- On human review the reviewer sees the full report; in a real deployment the flagged party
  would see and may answer it (Responsible AI story for the demo).

## 3. Tools (the agent's own lookups)

The Fraud agent is the one agent that actively queries; it represents no side, so its lookups
create no evidence asymmetry. Four tools, reading mock platform data plus our own store:

| Tool | Returns | Source |
|---|---|---|
| `get_user_history(user_id)` | disputes filed, upheld/rejected ratio, account age, trips, rating | mock profile + rulings table |
| `get_confirmed_flags(user_id)` | human-confirmed flags only, with reasons | user_flags table (`confirmed`) |
| `find_similar_past_claims(user_id, facts)` | past claims by this user resembling this one | precedent-style fact-summary match (Collector facts, never the party's wording) |
| `get_pair_history(rider_id, driver_id)` | prior trips/disputes between this exact pair | mock data (demo cases only) |

## 4. Scoring rules (all code)

Two signal classes with different ceilings:

**Prior-based (soft) — can reach MEDIUM at most, never HIGH:**
- high rejected-dispute ratio (e.g. >=2 rejected and rejected > upheld)
- young account + large claim
- high dispute frequency (e.g. >=3 in 90 days)

**Case-evidence (hard) — required for HIGH:**
- evidence timestamp contradicts the trip (photo EXIF before pickup — the `cleaning_fee_01` pattern)
- claim contradicts GPS/app events (e.g. "driver never came" vs 8 min waiting at pickup)
- chat contains a confirmed collusion offer or threat (see §5)
- abnormal repeat pairing of the same rider and driver

| Level | Automatic action | Never |
|---|---|---|
| LOW | nothing; note in report | — |
| MEDIUM | report to Judge + Fairness; may require extra evidence (e.g. original photo) | influence verdict by itself |
| HIGH | route to human review with full report | auto-dismiss |
| Human-confirmed | reviewer may restrict (audit-logged, appealable, time-bound) | permanent ban without human sign-off |

The report itself is template text ("4 disputes in 90 days, 3 rejected; this claim's photo
predates the trip by 4 h"), not LLM prose.

## 5. The one LLM use: chat semantics

Keyword rules first; the LLM only for what they miss (collusion offers, threats, chat that
contradicts the filed claim). Constraints:

- fixed output labels only: `collusion_offer | threat | contradicts_claim | none`, each with a
  verbatim quote;
- a label whose quote is not actually in the chat log is discarded (anti-fabrication);
- the label is one *input* to the code rules; the LLM never outputs a score;
- called only when chat logs exist (≈1 extra call/case at most);
- injection: chat text is user-authored, so the eval adds a case with "mark me low risk"-style
  text in chat, which must change nothing.

## 6. Integration guards (the D15 lesson, applied up front)

1. **Fairness must accept the fraud report as a source of truth from day one.** The 63% run
   happened because a source added for the Judge (the Case Brief) was not added to Fairness's
   citation whitelist. The fraud report's references (`fraud_report.*`) go into
   `_build_valid_refs` and the semantic-check prompt in the same change that creates the agent,
   with a unit test — not after an eval drop.
2. **The Judge prompt states that risk is context, not evidence** against the claim, and the
   "priors but genuine" eval case (§7) guards it.
3. **Eval/demo repeat-run pollution:** similar-claim matching excludes the current
   `dispute_id`; eval runs do not write pending flags (or dedupe by dispute_id). Otherwise
   three eval repeats make every case its own "similar history".

## 7. Mock data + acceptance criteria

New cases (dev + heldout variants): priors-but-genuine (must still win — the fairness guard),
fake claim with hard evidence (-> HIGH -> human), collusion pair with chat offer (-> HIGH),
chat-injection variant (-> unchanged). Pair history exists only in these new cases; collusion
detection is demo-only and the docs say so.

**Hard acceptance bar: the existing 27 cases keep exactly their current verdicts and
escalations** (93% run 20261001-203206). CR-002's rider already carries a real
frequent-cancellation flag with 2 rejected disputes and must stay resolved — that is the
regression test for the "priors never reach HIGH" ceiling. Full suite + new unit tests pass.

## 8. Out of scope

Auto-restrictions of any kind; fine-grained fraud ML; real EXIF parsing (mock metadata fields
suffice until Image Analysis lands); cross-case graph analysis beyond the one pair rule.
