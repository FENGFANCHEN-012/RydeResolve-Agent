# RydeResolve demo script (5-8 min)

Follows the handbook's video outline: project overview, core agent features and how they are
used, a short reflection on the build and CodeBuddy tips. Target length about 7 minutes.

## Before recording

- Site: http://43.134.17.192 (enter the demo access code). Dashboard tab "Dispute Resolution".
- The three moments below are replayed from the runs that produced them, so the demo never depends
  on provider quota or on a rerun ruling differently. On the server, once:

  ```bash
  cd ~/ryderesolve
  echo 'EXTRA_DISPUTE_DIRS=data/eval_cases/fresh2_sonnet' >> .env   # makes case F2-17 loadable
  .venv/bin/python scripts/import_demo_traces.py \
      data/eval/20261012-115556/traces/RD-001_r1.json \
      data/eval/20261012-213702-fresh2/traces/F2-17_r1.json \
      data/eval/20261012-115556/traces/SI-001_r1.json
  sudo systemctl restart ryderesolve
  ```

  The eval traces are not in git (`data/eval/` is local); copy the three files to the same paths
  on the server first (`scp`).
- They appear under "Saved runs" as demo-1-RD-001, demo-2-F2-17, demo-3-SI-001.
- Optional live run: press "Run agents" on RYDE-DEMO-001 to show it really runs (about 90 s). Have
  the replay ready in case the provider is slow.

## 0:00-1:00 Problem and idea

Say:
- "Ride-hailing platforms handle thousands of disputes a day. Today a person reads GPS, chat logs,
  receipts and policy for each one: 24 to 72 hours, and two agents can rule differently on the
  same facts."
- "RydeResolve resolves standard disputes in about two minutes with a team of agents: a rider
  advocate, a driver advocate and a judge, plus evidence, fraud and fairness agents."
- "Our rule: when the system cannot prove its ruling from the records, a person decides. It
  would rather hand a case over than pay out on a wrong ruling."

Show: the architecture figure (`docs/architecture.png`), 15 seconds, pointing at the flow from
evidence to advocates to judge to code checks.

## 1:00-3:00 Case 1: route deviation, resolved automatically (demo-1-RD-001)

Complaint: "My driver missed the exit on the AYE... charged $18.20 instead of the $14.50 quoted.
I want the extra $3.70 refunded."

Replay and narrate each step as it lights up:
1. Collector: code tools read GPS, fare, app events and chat. Each finding names its record. It
   finds the route-deviation alert, 10.4 km against 8.2 km planned, fare S$18.20 against S$14.50.
2. Classifier: route deviation, priority P1, no safety issue.
3. Rider advocate and driver advocate: each builds its side's case and cites policy. Open the
   debate panel: the driver's side admits the missed exit in the chat.
4. Judge: upheld, refund S$3.70, confidence 0.92, with the reasons and the facts it rests on.
5. Code Judge: checks that every decisive fact is verified on a clean record and that S$3.70 is
   arithmetic on record figures (18.20 - 14.50). Passes.
6. Fairness audit passes; the executor sends the outcome to both rider and driver.

Say: "This is the majority path: in our blind tests about 82% of standard disputes close like
this, in about two minutes."

## 3:00-4:45 Case 2: the code Judge stops a wrong refund (demo-2-F2-17)

Complaint: "The app told me the driver was 8 minutes away. He was still not here 23 minutes later
so I cancelled and was charged $5.00."

The catch: the record of when the driver was assigned has a logged data problem, and the ETA shown
at assignment is missing. The answer key says a person must decide.

Narrate:
1. Collector flags a gap on `app_events[1]` (driver assignment).
2. Judge, first draft: refund S$5.00, confidence 0.62. It rests on "cancelled 22.9 minutes after
   matching", which comes from the questioned record.
3. Code Judge blocks it and sends it back with the problems listed.
4. Judge, second draft: still S$5.00, confidence now 0.85. It has simply deleted the questioned
   record from its list of facts.
5. Code Judge: "pays the same as the draft the check blocked, but no longer lists the questioned
   record" -> human review.

Say: "The model raised its own confidence from 0.62 to 0.85 without any new evidence. That is why
we never let the model check itself: code does. We found this loophole on our sealed test set,
closed it, and it stopped this refund on a fresh set nobody had seen."

Show: the review desk (`/review.html`): an escalated case with the full agent chain, the reason it
was escalated, and the reviewer's buttons. A reviewer's decision can become a precedent after an
evaluation gate.

## 4:45-5:45 Case 3: a safety report goes straight to a person (demo-3-SI-001)

Complaint: "The driver kept commenting on my body... said he knows where I stay. I feel unsafe."

Narrate: the classifier's safety scan marks it P0 in under a second; the Safety agent sends it to a
person now. No advocate debates it, no automatic refund. "Safety is never automated."

## 5:45-6:45 How we know it works

Show the results table from the README:
- 38 dev and held-out cases: 33 correct, 0 wrong payouts.
- Fresh blind set (20, written by another model without seeing the code): 16 correct, 0 wrong payouts.
- Sealed set (23, run once, never used for a fix): 16 correct, 1 wrong payout, which led to the
  fix shown in case 2.
- A second fresh set after that fix: 13 correct, 1 wrong payout (a rule's wording misread; open).

Say: "We publish the misses as well. Most misses are cases handed to a person, which costs time,
not money."

## 6:45-7:30 Reflection and CodeBuddy

Say (pick two or three):
- "We built with CodeBuddy throughout: <your concrete tip, e.g. asking it to replay saved runs
  before changing a check>."
- "Lesson: put deterministic checks where the model is weakest: time arithmetic, amounts, and
  whether a record can be trusted."
- "Every change is logged with what, why and the measured effect (docs/08), and tested on cases
  written after the change."

Close: "RydeResolve: fair, explainable ride-dispute rulings in minutes, not days."
