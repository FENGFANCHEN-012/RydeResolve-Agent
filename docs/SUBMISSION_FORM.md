# Submission form: paste-ready text (deadline 16 Oct 2026)

One block per field of the handbook's submission list (docs/01_PROJECT_REQUIREMENTS.md, p.37).
Figures are from docs/08_DESIGN_DECISIONS.md (D38-D50) and README; change nothing without checking there.

## Project title (required)

RydeResolve-Agent

## Short blurb (required, under 10 words)

Fair, explainable ride-dispute rulings in minutes, not days.

## Project description (required)

### Overview: scenarios, users, value

RydeResolve settles rider-driver disputes on Ryde with a team of AI agents. A rider or driver files a
complaint (a longer route, a no-show fee, a cleaning charge with a photo, a surge fare, an unsafe
driver). The system gathers the trip's evidence (GPS, fare, chat, app events, profiles, photos), a
rider advocate and a driver advocate each argue their side from that evidence and the organisers'
Ryde Dispute Resolution Policy v2.1, and a Judge rules on every request with its reasons, the v2.1
sections it applies and a confidence score. Code, not the
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
1. Collector: code tools read the platform records in the organisers' sample format (trip, GPS,
   chat, app events, fare breakdown, surge log, recommended route, traffic incidents) and report
   facts, conflicts and data gaps, each naming its record, including the v2.1 checks (surge rose
   without notice, excess over the recommended route, an incident on that route, a message and a
   call before a no-show cancel). The samples' own analysis sections are removed first. Photos are checked twice: code
   reads each photo's capture time and GPS against the trip, editing software and reuse in another
   case; a vision model (qwen on Groq) says what the photo shows and can only raise doubts. Chat
   tone: code labels each message (frustrated, angry, distress; agree, object), a model re-checks
   only doubtful ones (sarcasm, negation, other languages). Tone goes to the reviewer and the notice
   wording, never to the advocates or the Judge: who sounded angrier is not evidence.
2. Classifier: dispute type and urgency; safety reports go straight to a person.
3. Case Brief: one shared dossier for every agent, computed without an LLM: the v2.1 sections the
   case needs, in full, plus Help Centre clauses retrieved by hybrid search (Qdrant).
4. Fraud agent: code risk signals plus evidence-grounded chat labels, seen by the Judge and the
   audit, never by the advocates.
5. Rider and driver advocates argue and rebut; a Policy agent checks compliance.
6. Judge (gpt-oss-120b): rules on each request, names the facts the ruling turns on and gives any
   refund as plain arithmetic.
7. Code checks: every decisive fact must be verified on a record nothing contradicts; a refund
   must be arithmetic on record figures (a route refund no more than the excess distance fare); no
   payment rests on a doubted photo; a failing draft goes back to the Judge once, then to a person.
   A policy gate then applies v2.1's routing in code: safety incidents, disputes above S$50, a fraud
   flag without 95% confidence and a rider contesting damage go to a person. Then a Fairness audit,
   which also notes a ruling whose reasons lean on a party's manner.
8. Executor: simulated refund or penalty and a notice to each party (English, Chinese, Malay, Tamil);
   an upset party's notice opens with one acknowledging line, the outcome unchanged.

How prompts drive the AI: every agent has a narrow role, shared grounding rules (no invented
evidence, amounts or policy; no protected characteristics) and a strict JSON output schema. Code
parses each answer, drops any policy citation that was not retrieved, and checks the Judge's facts
and arithmetic against the records before the next step sees it.

Human in the loop: a review desk shows escalated cases with the full agent chain and each chat
message's tone; reviewer
decisions can become precedents only after approval and an evaluation gate. A case editor lets
anyone build or copy a case (trip, profiles, both sides' chat, rules, photos) and watch it run.

### Business value, with measured figures

Measured with Cerebras gpt-oss-120b, one run per case, on cases with answer keys written before the
runs (several sets written blind by another model, one sealed set run once):
- Speed: about 89 seconds per dispute, against 24 to 72 hours today; safety reports reach a person
  in under a second.
- Automation: under Policy v2.1, 78% of the disputes the policy lets AI decide (28 of 36 in a
  52-case regression) closed with no human, in about 89 seconds each.
- Accuracy under v2.1: the organisers' samples DISP-001..003 all right; a 30-case blind set in their
  full format 25/30; 52 earlier cases re-run with keys re-checked against v2.1: 44/52 with no wrong
  payout in that run (15 Oct). Half of those misses ran on a debate with one side's call failed
  (provider busy); with a retry added, 3 of them got the right verdict on re-run, one with too small
  an award (S$2.80 of S$8.80). A re-run on the submitted code (16 Oct) gave 45/52, but 5 automatic
  rulings were wrong, 3 of them cases with a logged data problem that must go to a person: the Code
  Judge catches a questioned record only when the Judge lists it, so the slip happens about one run
  in two on those cases. One cause added that day is removed; the next fix checks the questioned
  record in code (D59). Every wrong payout found, and its fix, is published.
- Cost: about US$0.017 per dispute on gpt-oss-120b (Judge about 9,000 tokens in / 1,600 out; six
  other calls about 24,000 in / 6,000 out). At 1,000 disputes a day (an illustration, not a Ryde
  figure): about US$520 a month as today; about US$1,400-2,100 with the Judge on Claude Sonnet 5.5;
  about US$2,400-3,900 with the Judge on Claude Opus 5.5, the other agents staying on gpt-oss-120b.
  An open model such as DeepSeek on the company's own GPU server has no per-token fee.
- Beyond the demo: the live site runs on one small Tencent Lighthouse server; production adds
  instances behind a load balancer, Postgres and a job queue. A model change is re-evaluated on the
  same sets before it goes live.
- 78% automation of the disputes AI may decide removes the first manual read from most of them; the
  rest reach a person with the case built.

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
