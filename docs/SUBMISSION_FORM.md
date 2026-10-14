# Submission form: paste-ready text (deadline 16 Oct 2026)

One block per field of the handbook's submission list (docs/01_PROJECT_REQUIREMENTS.md, p.37).
Figures are from docs/08_DESIGN_DECISIONS.md (D38-D49) and README; change nothing without checking there.

## Project title (required)

RydeResolve-Agent

## Short blurb (required, under 10 words)

Fair, explainable ride-dispute rulings in minutes, not days.

## Project description (required)

### Overview: scenarios, users, value

RydeResolve settles rider-driver disputes on Ryde with a team of AI agents. A rider or driver files a
complaint (a longer route, a no-show fee, a cleaning charge with a photo, a surge fare, an unsafe
driver). The system gathers the trip's evidence (GPS, fare, chat, app events, profiles, photos), a
rider advocate and a driver advocate each argue their side from that evidence and Ryde's official
policy, and a Judge rules on every request with its reasons and a confidence score. Code, not the
model, then checks the ruling before any money moves; if the ruling cannot be proven from the records,
the case goes to a person with the whole file already built.

Users: riders and drivers get a ruling and a plain-language explanation in about two minutes; Ryde's
support staff review only the cases the system should not decide alone; Ryde gets the same rule
applied the same way every time, with a full audit trail.

### Real-world pain points

- Cost: thousands of dispute tickets a day, each read by a person.
- Speed: 24 to 72 hours per dispute today.
- Inconsistency: two agents can rule differently on the same facts.
- Churn: users who feel unfairly treated leave. Ryde charges drivers 0% commission, so a wrongly
  applied fee hits a driver's whole take-home pay.

### Business and technical architecture, and how prompts drive the AI

Pipeline (LangGraph, FastAPI, every step streamed live to the dashboard):
1. Collector: code tools read GPS, fare, chat, app events, profiles and the trip's own rules, and
   report facts, conflicts and data gaps, each naming its record. Photos are checked twice: code
   reads each photo's capture time and GPS against the trip, editing software and reuse in another
   case; a vision model (qwen on Groq) says what the photo shows and can only raise doubts.
2. Classifier: dispute type and urgency; safety reports go straight to a person.
3. Case Brief: one shared dossier for every agent, computed without an LLM, with clauses retrieved
   from Ryde's official policy text (Qdrant hybrid search).
4. Fraud agent: code risk signals plus evidence-grounded chat labels, seen by the Judge and the
   audit, never by the advocates.
5. Rider and driver advocates argue and rebut; a Policy agent checks compliance.
6. Judge (gpt-oss-120b): rules on each request, names the facts the ruling turns on and gives any
   refund as plain arithmetic.
7. Code Judge and Fairness audit: every decisive fact must be verified on a record nothing
   contradicts, a refund must be arithmetic on record figures, a doubted photo always goes to a
   person; a failing draft goes back to the Judge once, then to a person.
8. Executor: simulated refund or penalty and a notice to each party (English, Chinese, Malay, Tamil).

How prompts drive the AI: every agent has a narrow role, shared grounding rules (no invented
evidence, amounts or policy; no protected characteristics) and a strict JSON output schema. Code
parses each answer, drops any policy citation that was not retrieved, and checks the Judge's facts
and arithmetic against the records before the next step sees it.

Human in the loop: a review desk shows escalated cases with the full agent chain; reviewer
decisions can become precedents only after approval and an evaluation gate. A case editor lets
anyone build or copy a case (trip, profiles, both sides' chat, rules, photos) and watch it run.

### Business value, with measured figures

Measured with Cerebras gpt-oss-120b, one run per case, on cases with answer keys written before the
runs (several sets written blind by another model, one sealed set run once):
- Speed: about 98 seconds per dispute, against 24 to 72 hours today; safety reports reach a person
  in under a second.
- Automation: 82% of standard disputes (67 of 82) closed with no human on the four main sets.
- Accuracy: 102 of 133 rulings correct across seven test sets. Most misses were cases handed to a
  person, which costs review time, not money; 5 wrong payouts in 133 runs (the largest S$100,
  which led to the rule that a doubted photo always goes to a person). All misses are published.
- Cost: about 29,000 tokens, roughly US$0.01-0.02, per dispute.
- Illustration (not a Ryde figure): at 1,000 disputes a day, 82% automation removes the first
  manual read from about 820 tickets a day.

## CodeBuddy / WorkBuddy conversation history (required, at least 3 screenshots)

Upload from `proof of usage of codebuddy/` (28 screenshots). Suggested if a limit applies:
05, 07, 09, 10, 19, 21 (diagnosis before a change, the autonomy decision, the A/B test).

## Cover image (required, 16:9, 380 x 216)

`docs/cover/cover_380x216.png` (larger: `docs/cover/cover_1520x864.png`).

## Demo video (optional, 5-8 min)

Script `docs/DEMO_SCRIPT.md`, narration `docs/DEMO_NARRATION.md`.

## Project link (optional, earns bonus points)

http://43.134.17.192 (access code: give the DEMO code, not the admin code)

Source code: https://github.com/FENGFANCHEN-012/RydeResolve-Agent (merge PR #24 into main first)

## Architecture diagram (must include, p.26)

`docs/architecture.png` (vector: `docs/architecture.svg`).
