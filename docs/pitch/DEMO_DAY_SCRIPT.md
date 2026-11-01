# Demo Day: 4-minute talk + 1-minute Q&A, product shown inside the slides

Deck: `RydeResolve_DemoDay_v3.pptx` (this folder; v2 had no problem-statement or engineering
slides). Clips: `clips/` (also embedded in the deck).

Story line: Ryde's problem and its four pain points → what we built against each one → see it
running (four demos) → the engineering decisions behind it → proof → next step.
Replaces the live browser demo of `SPEAKERS.md`: nobody switches windows on stage. Each demo slide
plays a muted recording of the live site by itself; the speaker talks over it.

## Run of show

| Slide | Time | Speaker | On screen | Presenter does |
|---|---|---|---|---|
| 1 Title | before start | — | logo | wait for the host |
| 2 Problem statement | 0:00–0:20 | 1 | Ryde's brief + 4 pain points | — |
| 3 Pain point → what we built | 0:20–0:45 | 1 | 4 rows: pain → answer → how | — |
| 4 How it works | 0:45–0:55 | 1 | agent flow diagram | — |
| 5 Demo 1 DISP-001 | 0:55–1:35 | 1 | clip 44 s + 3 callouts | advance once; clip starts itself |
| 6 Demo 2 F2-17 | 1:35–2:10 | 2 | clip 42 s + 3 callouts | advance once |
| 7 Demo 3 SI-001 | 2:10–2:22 | 2 | clip 16 s + 3 callouts | advance once |
| 8 Demo 4 people | 2:22–2:47 | 2 | clip 29 s + 3 callouts | advance once |
| 9 Engineering decisions | 2:47–3:15 | 3 | 6 design decisions | — |
| 10 Results | 3:15–3:35 | 3 | results table | — |
| 11 Next step | 3:35–4:00 | 3 | shadow mode, close line | — |
| Q&A | 4:00–5:00 | 3 routes | slide 11; slide 12 = architecture backup | — |

Rules
- One clicker, held by whoever speaks. Press "next" only when you finish a slide; never click
  on a video (that pauses it).
- If a clip ends before you finish, it stays on its last frame. If you finish first, advance anyway.
- The clips are muted and in the deck file, so no Wi-Fi is needed. Copy the .pptx to the venue
  laptop and play it once there before the rehearsal (2 Nov 16:00).
- Spare: the four `clips/*.mp4` play in any video player.

## What each clip shows (seconds from the start of the clip)

All clips are recorded from http://43.134.17.192 using "Replay a saved run" (no model is called).
A red ring marks every click.

**Clip 1, DISP-001 (44 s)** — 0–5 pick replay `demo-7-DISP-001`, agents light up · 5–8 verdict:
Partially upheld, S$3.44 · 8–14 Collector (records) · 14–19 rider and driver advocates · 19–28
Judge, then the verdict again · 28–33 code checks · 33–44 notices, click 中文, click Melayu.

**Clip 2, F2-17 (42 s)** — 0–6 pick replay `demo-2-F2-17` · 6–10 "Escalated to human review" ·
10–20 Judge (Arbitrator) panel · 20–30 Debate panel (where the code judge blocks the drafts) ·
30–36 Fairness · 36–42 Human review.

**Clip 3, SI-001 (16 s)** — 0–4 pick replay `demo-3-SI-001` · 4–8 "Escalated to human review,
P0" · 8–13 Classifier: P0, debate skipped · 13–16 the safety notice.

**Clip 4, people in the loop (29 s)** — 0–2 dashboard · 2–3 click "Review desk →" (top right) ·
3–8 review queue + case SQ-001 + Tencent ADP assistant · 8–17 click CR-001, its facts in dispute ·
17–29 status page `status.html?case=23`: Received → Sent to a person → Final decision: not yet.

## The words

### Slide 2, the problem statement (Speaker 1, 0:00–0:20)
> "Ryde asked for a system that rules rider-driver disputes fairly, fast and without a person for
> most standard cases. Today a dispute takes 24 to 72 hours, every one is read by hand, two agents
> can rule differently on the same facts, and people who feel treated unfairly leave. Our rule:
> automate what can be proven from the records; a person decides the rest."

### Slide 3, pain point → what we built (Speaker 1, 0:20–0:45)
> "Each pain point has an answer you can check. 24 to 72 hours becomes under two minutes. Cost:
> about 1.7 US cents a dispute, and a person only for what cannot be proven. Inconsistency: every
> ruling applies the same policy by section, and code verifies every fact and amount. Fairness:
> both sides get an advocate, both get the reasons in their language, a status page, and an appeal
> where the AI was unsure."

### Slide 4, how it works (Speaker 1, 0:45–0:55)
> "Behind it: a rider advocate, a driver advocate and a judge, with evidence, photo, fraud and
> fairness checks around them, and code checking every fact. Here it is running."

### Slide 5, Demo 1 (Speaker 1, 0:55–1:35)
> "This is the organisers' own route-deviation sample. [agents light up] Code first reads the
> records: 24.8 km driven against 20.5 recommended, and a vehicle fire on the PIE during the trip.
> [advocates] The rider's advocate: she asked at 13:24 and got no answer. The driver's advocate:
> the PIE was on fire. Both cite the policy. [verdict] The judge: partially upheld, S$3.44. He
> rerouted for a good reason but never told her, so the excess-distance fare comes back. Every fact
> is traced to a record, it is under S$10, so it is final. [notices] Both parties get the notice in
> four languages."
>
> Handover: "But what happens when the AI gets it wrong?"

### Slide 6, Demo 2 (Speaker 2, 1:35–2:10)
> "This is the case we are proudest of, because the AI was wrong and caught itself. The rider
> cancelled after 23 minutes and was charged S$5, but the driver-assignment record has a logged
> data problem. [Judge panel] First draft: refund S$5 at 62% confidence, resting on that record.
> The code judge blocks it. [Debate panel] Second draft: the same S$5, now 85%, with no new
> evidence. Code stops it again and a person decides. Code checks the model; the model never
> checks itself."

### Slide 7, Demo 3 (Speaker 2, 2:10–2:22)
> "A rider writes: he kept commenting on my body and said he knows where I stay. P0 in under a
> second: no debate, no judge, straight to a person, and no money moves. On two blind harassment
> sets: 10 out of 10 and 6 out of 6."

### Slide 8, Demo 4 (Speaker 2, 2:22–2:47)
> "Every case the AI hands over lands on the review desk: why it stopped, the facts in dispute,
> and a Tencent ADP assistant for policy questions. The person decides. [status page] Riders and
> drivers get a status page with every step, without the AI's internals. And they can appeal where
> the AI was unsure, below 80% confidence, once, with new evidence. The AI checks it first; if it
> is still unsure, a person decides. Just saying 'I disagree' does not reopen a case."
>
> Handover: "So how do we know it works?"

### Slide 9, engineering decisions (Speaker 3, 2:47–3:15)
> "What we are proudest of is engineering, not prompts. Code checks the model: every fact and
> amount is verified against a record before money moves. When it cannot be proven, a person
> decides: 52 cases, zero wrong payouts. Safety is decided in code; the model can never lower it.
> Advocates only see what their role needs. Every step is replayable and every ruling is in a
> hash-chained audit log. And it is ready for Ryde's API in shadow mode at under two cents a
> dispute."

### Slide 10, results (Speaker 3, 3:15–3:35)
> "The organisers' three samples: 3 of 3. A 30-case blind set in their format: 25 of 30. 52 cases
> under the current policy: 44 of 52 with zero wrong payouts. Most misses are cases handed to a
> person: that costs minutes, not money."

### Slide 11, next step (Speaker 3, 3:35–4:00)
> "The next step is real data, and that is already built: one setting connects Ryde's API in
> shadow mode. It rules next to the human, pays nothing, and earns the right to decide small cases
> alone once agreement is high. RydeResolve: fair, explainable ride-dispute rulings in minutes, not
> days. Thank you."

## Q&A (1 minute: two questions at most, 20–25 s per answer)

Speaker 3 takes the question and passes it on.

| Question | Who | Answer (short) |
|---|---|---|
| What if the AI is wrong? | 2 | Money moves only when code verifies every fact and amount against a record. Otherwise a person decides. 52 cases, zero wrong payouts. |
| Why can't everyone appeal? | 2 | The losing side almost always would, and that undoes automation. Appeals are for rulings under 80% confidence, once, with new evidence; the AI re-checks first. Safety cases never need an appeal: they go to a person from the start. |
| How does it connect to Ryde? | 1 | One client reads Ryde's API and maps it to the organisers' format. It runs in shadow mode: rules next to a person, pays nothing. The field map is our guess until we see Ryde's field list. |
| Where do the policy rules come from? | 1 | Ryde's published policies. Honest: the demo uses our paraphrase, gaps marked; the official-text version is on a separate branch. Every ruling cites its section. |
| Privacy? | 3 | Demo data only. A deployment masks names, phones and plates before any external model call, or runs the model in-house. The status page shows parties no AI internals. |
| Why Tencent Cloud? | 1 | Lighthouse server in Singapore, the policy assistant on Tencent ADP (Hunyuan), built with CodeBuddy. |
| Does it learn? | 2 | Only through people: a reviewer's decision becomes a precedent after an evaluation gate shows results do not get worse. |

## If something goes wrong
- A clip does not play: click once on the video (it starts), keep talking.
- The deck will not open: play `clips/*.mp4` in order from a file window.
- Do not open the live site on stage unless all of the above fail; if you do, replays only,
  never "Run agents".

## Re-recording the clips
The recorder clicks the live site exactly as above (scratchpad `record/record.js`, Playwright,
1440×810, red click rings). Re-record after any UI change to the dashboard, then rebuild the deck
(`build_deck.py`). Both are kept outside the repo; ask Claude to rerun them.
