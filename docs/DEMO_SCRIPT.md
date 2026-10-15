# RydeResolve demo script (5-8 min)

Follows the handbook's video outline: project overview, core agent features and how they are
used, a short reflection on the build and CodeBuddy tips. Target length about 7 min 45 s.

## Before recording

- Site: http://43.134.17.192 (enter the demo access code). Dashboard tab "Dispute Resolution".
- The recorded moments are replayed from the runs that produced them, so the demo never depends
  on provider quota or on a rerun ruling differently. They are already on the server under
  "Replay a saved run": demo-1-RD-001, demo-2-F2-17, demo-3-SI-001, demo-4-IM-04 (genuine photo),
  demo-5-IM-12 (AI-generated photo), demo-6-DISP-003 and demo-7-DISP-001 (the organisers' samples,
  run under Policy v2.1 on 15 Oct). To add more, copy the eval trace to the same path on the
  server (`data/eval/` is not in git) and run `scripts/import_demo_traces.py <trace>` there, then
  restart the service.
- The case editor segment (5:00) is a live run, about 90 s of agent time: record it once and cut
  the waiting in editing. It needs the access code and spends about US$0.015 of LLM quota.

## 0:00-0:50 Problem and idea

Say:
- "Ride-hailing platforms handle thousands of disputes a day. Today a person reads GPS, chat logs,
  receipts, photos and policy for each one: 24 to 72 hours, and two agents can rule differently on
  the same facts."
- "RydeResolve resolves standard disputes in about two minutes with a team of agents: a rider
  advocate, a driver advocate and a judge, plus evidence, photo, fraud and fairness checks. It
  applies the organisers' Ryde Dispute Resolution Policy v2.1, and its routing rules run in code."
- "Our rule: when the system cannot prove its ruling from the records, a person decides."

Show: the architecture figure (`docs/architecture.png`), 15 seconds, pointing at the flow from
evidence and photos to advocates to judge to code checks.

## 0:50-2:20 Case 1: the organisers' own sample DISP-001 (demo-7-DISP-001), then DISP-003 (demo-6)

Complaint (the organisers' route-deviation sample): Orchard Central to Changi T3, "the driver took a
significantly longer route ... did not inform me ... I am requesting a refund of the excess fare."

Replay and narrate each step as it lights up:
1. Collector: code reads the organisers' records. 24.8 km against the recommended PIE route's
   20.5 km: +4.3 km, beyond Policy v2.1's 1 km tolerance; the fare breakdown records an excess
   distance fare of S$3.44. A traffic record shows a vehicle fire on PIE eastbound, 13:05-13:50,
   active during the trip and on the recommended route.
2. Advocates argue; the chat shows the rider asking at 13:24 and the driver not giving the reason.
3. Judge: partially upheld, S$3.44, citing v2.1 s1.2 (notify the rider) and s1.3 (the refund
   matrix: rerouted for traffic but not informed = the excess distance fare, not tolls or time).
4. Code checks: facts verified, S$3.44 is a record figure and does not exceed the excess distance
   fare; the v2.1 gate finds nothing that needs a person (under S$10, no safety issue). Executed.

Scroll to "Sent to both parties" and click 中文, then Melayu (15 s): the two notices are rebuilt
by code from the ruling's fields in the chosen language (`POST /api/notices`, no model call, works
on a replay).

Then 20 seconds on demo-6-DISP-003 (the organisers' surge sample): surge rose from 1.0x to 1.5x
before pickup, `rider_notified: false`, the surgeable subtotal unchanged, so the S$4.50 difference is
all surge; v2.1 s3.3 refunds it, and under S$10 the AI ruling is final.

Say: "These are the organisers' own samples, ruled by their own policy, section by section."

## 2:20-3:50 Case 2: the code Judge stops a wrong refund (demo-2-F2-17)

Complaint: "The app told me the driver was 8 minutes away. He was still not here 23 minutes later
so I cancelled and was charged $5.00." The record of the driver assignment has a logged data
problem, and the ETA shown at assignment is missing.

Narrate:
1. Collector flags a gap on `app_events[1]` (driver assignment).
2. Judge, first draft: refund S$5.00, confidence 0.62, resting on that questioned record.
3. Code Judge blocks it and sends it back with the problems listed.
4. Judge, second draft: still S$5.00, confidence now 0.85; it simply deleted the questioned record.
5. Code Judge: "pays the same as the draft the check blocked" -> human review.

Say: "The model raised its own confidence with no new evidence. That is why code checks the model,
never the model itself."

Show briefly: the review desk (`/review.html`) with this case, the reason it was stopped, and the
reviewer's buttons. A reviewer's decision can become a precedent after an evaluation gate.

## 3:50-5:00 Case 3: photo evidence (demo-4-IM-04, then demo-5-IM-12)

demo-4-IM-04: a driver claims a S$40 cleaning fee for muddy shoes, with a photo.
- Show the photo in the case brief, then the Collector panel: code reads the photo's own data:
  taken 5 minutes after drop-off, 30 m from the drop-off point; no editing tag, and the same file is
  in no other case. The ImageAnalyst (vision model) sees muddy sneakers on the floor mat, matching
  the claim.
- The fee stands, automatically.

demo-5-IM-12: a driver claims S$70 for a seat stain.
- The photo's time and place look right (8 minutes after drop-off, 20 m away), but the vision model
  sees a clean seat and an AI generator's watermark.
- The case goes to a person.

Say: "Photos are checked twice: code checks when and where it was taken and whether it was edited
or reused; a vision model checks what it shows. The vision model can only raise doubts, never
approve money. And a doubted photo always goes to a person, whichever side it would favour."

## 5:00-6:00 Try it yourself: the case editor (live)

1. Open demo case IM-04 (the genuine photo) and press "Copy & edit".
2. In Photos, change the photo's "Taken at" to 30 minutes before pickup. Save: a new case CU-xxxxxx
   appears and is selected.
3. Run agents (cut the waiting). The Collector flags "photo taken before the trip began". The
   rider is not charged: under v2.1 s4.4 the claim is rejected for evidence that is not linked to the
   trip, or the case goes to a person; no payment can rest on a doubted photo. (Rehearse once: which
   of the two you get varies.)

Say: "Judges can build their own cases here: trip, profiles, both sides' chat, rules and photos,
and watch every agent work on them."

## 6:00-6:20 Case 4: a safety report goes straight to a person (demo-3-SI-001)

Complaint: "The driver kept commenting on my body... said he knows where I stay. I feel unsafe."
The safety scan marks it P0 in under a second; it goes to a person now. "Safety is never automated."

## 6:20-7:00 How we know it works

Show the results table from the README:
- Under Policy v2.1: the organisers' samples 3/3; a 30-case blind set in their full format 25/30;
  52 earlier cases re-run with keys re-checked against v2.1: 44/52, 0 wrong payouts.
- Before v2.1: 38 dev and held-out cases: 33 correct, 0 wrong payouts.
- Blind sets written by another model that never saw the code: 16/20 and 13/20; a sealed set run
  once: 16/23. Each wrong payout led to a logged fix and a new blind set written for it.
- Blind photo sets: 8/12, where one S$100 fee was refunded on a doubted photo; after the fix that
  sends every doubted photo to a person, 9/10 with no fee confirmed or removed on a doubted photo.
- A misread fee rule (the cancellation fee covers a no-show the driver cancels) was fixed; the three
  cases it got wrong are now right, and the new set for it scored 7/10, with two wrong payouts on
  other points that we publish.

Say: "Most misses are cases handed to a person, which costs time, not money. We publish the rest."

## 7:00-7:45 Reflection and CodeBuddy

CodeBuddy tips, each backed by a screenshot in `proof of usage of codebuddy/` (show one or two on
screen while speaking; edit the wording to your own):
- "Ask for a diagnosis before a change. Before giving the advocates their own evidence lookups, we
  had CodeBuddy explain how they get evidence today and write a change plan (screenshots 05-08)."
- "Ask about cost and risk, not just how to build it. When we asked about fully autonomous agent
  loops, CodeBuddy laid out the token, latency and testing cost, and we chose constrained autonomy:
  zero-token queries plus one LLM decision (09-12)."
- "Commit a baseline before an experiment. Before a token-saving change we made a rollback commit,
  ran an A/B test, found that truncating policy clauses hurt accuracy, and kept only the safe
  savings (19-21)."

Say (pick one or two):
- "Lesson: put deterministic checks where the model is weakest: time arithmetic, amounts, photo
  data, and whether a record can be trusted."
- "Every change is logged with what, why and the measured effect (docs/08), and tested on cases
  written after the change."

Close: "RydeResolve: fair, explainable ride-dispute rulings in minutes, not days."
