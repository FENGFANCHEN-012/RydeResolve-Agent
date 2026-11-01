# Demo Day: 4-minute talk + 1-minute Q&A, product shown inside the slides

Deck: `RydeResolve_DemoDay_v4.pptx` (this folder). Clips: `clips/` (also embedded in the deck).
v3 is kept for reference; v4 replaces it.

## Why this deck looks the way it does

- **The judges have seen our 7:49 video** (DISP-001, DISP-003, F2-17, the review desk, IM-04,
  IM-12, SI-001, results). We do not replay it. Old cases come back from a new angle (F2-17 as one
  static slide, IM-04 and IM-12 side by side); one case is new since the video (HR-03, harassment
  found in the chat of a cleaning-fee claim).
- **The rubric is 10 criteria × 10 points.** Four of them are about real use (Impact, Human-Centred
  Design, Feasibility, UX & Accessibility = 40 points); three about technology (AI Interaction,
  Technical Execution, Innovation = 30). So each feature is told as what it does for riders,
  drivers and Ryde, not only how it works.
- **Three features:** ① agents that work together, ② guardrails, ③ photo checks. One rule ties
  them together: *AI decides what the records prove, code guards the money, a person decides the
  rest.*
- **No live run on stage.** We do not control the venue laptop. Every demo is a muted recording of
  the live site playing a saved run (no model called), embedded in the deck.

## Run of show

| Slide | Time | Speaker | On screen | Rubric it serves |
|---|---|---|---|---|
| 1 Title / introduction | 0:00–0:10 | 1 | logo, product name, one-line pitch | — |
| 2 Hook | 0:10–0:22 | 1 | the AI-generated stain photo (IM-12) | Impact, Innovation |
| 3 Problem statement | 0:22–0:49 | 1 | Ryde's problem statement (quoted), 5 pains → 5 answers, the rule | Impact, HCD |
| 4 ① Agents, DISP-001 | 0:49–1:32 | 1 | clip 44 s + 3 callouts | AI Interaction, Technical |
| 5 ② Guardrails, F2-17 | 1:32–2:00 | 2 | draft 1 → blocked → draft 2 → person; 6 checks | Responsible AI, Technical |
| 6 ② Guardrails, HR-03 | 2:00–2:32 | 2 | clip 34 s + 3 callouts | Responsible AI, HCD |
| 7 ③ Photos, IM-04 / IM-12 | 2:32–3:13 | 2 | clip 50 s + both photos | Innovation, Responsible AI |
| 8 People | 3:13–3:44 | 3 | clip 29 s (review desk, status page) | HCD, UX & Accessibility |
| 9 Proof and next step | 3:44–4:05 | 3 | 4 results, shadow mode, cost, close line | Feasibility, Impact |
| Q&A | 4:05–5:00 | 3 routes | stay on slide 9 | — |
| 10–12 Backup | — | — | architecture, engineering decisions, results table | Q&A only |

Rules
- One clicker, held by whoever speaks. Press "next" only when you finish a slide; never click on a
  video (that pauses it).
- If a clip ends before you finish, it stays on its last frame. If you finish first, advance anyway.
- The clips are muted and inside the .pptx, so no Wi-Fi is needed. Copy the .pptx to the venue
  laptop and play it once there at the rehearsal (2 Nov 16:00).
- Spare: the `clips/*.mp4` files play in any video player.

## What each clip shows (seconds from the start of the clip)

**v4_agents_DISP-001.mp4 (44 s)**: 0–10 the saved run replays, the agents light up one after
another · 10–14 the full agent graph · 14–19 Collector, red box on the traffic record: vehicle fire
on the PIE during the trip · 19–27 debate: Passenger advocate, then Driver advocate · 27–36 Judge
and the ruling: partially upheld, S$3.44, 94% · 36–44 notices to both parties, switched to 中文.

**v4_harass_HR-03.mp4 (34 s)**: 0–9 replay, then "Escalated to human review: safety/legal issue" ·
9–12 red box on the rider's chat tone: "abusive" · 12–18 the chat check: "give me ur number … i wont
let u go" labelled abusive · 18–34 Safety step: tier "imminent", why ("sexual remarks and a vague
threat towards driver"), actions (do not re-match the pair, suspend the passenger pending review,
send safety guidance).

**v4_photos_IM-04_IM-12.mp4 (50 s)**: IM-04 0–12 replay and "Driver's claim upheld" · 12–19
Collector, red boxes: photo taken 5 min after drop-off, 0.03 km from the drop-off · 19–24 vision
model: muddy shoes, "matches claim: yes" · IM-12 24–36 replay and "Escalated to human review" ·
36–50 vision model: no visible stain, "pollinations.ai watermark; AI-generated image artifacts".

**demo4_people_review_status.mp4 (29 s)**: "Review desk" link → the desk with a handed-over case,
why it was handed over, the facts, the Tencent ADP policy assistant → the party status page.

## The words

Every feature is told the same way, over its clip: **what** the clip shows, **why** we built it
that way, and **what it changes** for riders, drivers and Ryde. The cues in [brackets] are seconds
into the clip; speak over the video, do not wait for it.

### Slide 1, introduction (Speaker 1, 0:00–0:10)
"Good afternoon. We are the Tung Tung team, and this is RydeResolve: AI agents that settle disputes
between Ryde riders and drivers, fairly, in minutes instead of days."

### Slide 2, hook (Speaker 1, 0:10–0:22)
"Take this photo. A driver claimed seventy dollars for a stained seat. There is no stain: an AI
image generator made it. RydeResolve caught it in seconds and handed it to a person."

### Slide 3, problem statement (Speaker 1, 0:22–0:49)
"Our problem statement, from Ryde: gather evidence, apply company policy and issue fair rulings,
quickly and transparently, without a person for most standard disputes. Today people wait days,
two staff can rule differently on the same facts, nobody explains why, evidence can be faked, and
a safety report can sit in a queue. So our rule: the AI decides what the records prove, code guards
the money, and a person decides the rest."

### Slide 4, ① agents that work together (Speaker 1, 0:49–1:32)
- [0–14 s, agents light up] "First, agents that work together. This is the organisers' own sample
  replaying: eleven agents, each with one job, passing the case along."
- [14–19 s, red box] "The collector finds the facts: 4.3 km off route, and a vehicle fire on the PIE."
- [19–27 s, debate] "Then a rider advocate and a driver advocate argue, each citing policy. Why? One
  AI asked for one answer tends to side with whoever complained. Two sides and a judge means both
  stories are heard."
- [27–36 s, ruling] "The judge: the detour was fair, but the rider was never told, so S$3.44 comes
  back."
- [36–44 s, 中文] "Both sides get the reasons in their own language. The impact: the same facts
  get the same ruling, with reasons, in about ninety seconds."
- Handover: "But an AI judge can be wrong."

### Slide 5, ② guardrails, F2-17 (Speaker 2, 1:32–2:00)
"Second, guardrails. The judge's first draft refunds five dollars at 62% confidence, resting on a
record the platform logged as faulty. Our code judge blocks it. The second draft: same five
dollars, now 85%, no new evidence. Code sends it to a person. Why code, not another AI? A model can
talk itself into being sure; a rule cannot. The impact: Ryde's money moves only when the facts and
the amount match a record."

### Slide 6, ② guardrails, HR-03 (Speaker 2, 2:00–2:32)
- [0–9 s, replay] "New since our video. A driver claims eighty dollars for a sticky seat. Routine,
  yet the system stops it and sends it to a person."
- [9–18 s, chat] "Why? It reads the whole trip, and in the chat the rider wrote: give me your number,
  I won't let you go."
- [18–34 s, safety] "The safety agent rates that imminent: no charge, the pair is never matched
  again, the passenger is held for review. Harassment hides inside ordinary claims, often against
  drivers, and a fee-only check would miss it. Blind tests: ten of ten."

### Slide 7, ③ photo checks (Speaker 2, 2:32–3:13)
- [0–12 s, IM-04] "Third, photos. Here a driver claims a cleaning fee for muddy mats."
- [12–19 s, red boxes] "First, code reads the photo's own data: taken five minutes after drop-off,
  thirty metres away."
- [19–24 s, vision] "Then a vision model looks: muddy shoes, matching the claim. The honest driver
  gets paid."
- [24–50 s, IM-12] "And the photo from the start: time and place pass, but the vision model sees a
  clean seat and an AI watermark, so the rider is not charged and a person decides. Why two layers?
  Fake photos are now one click away. The model can only raise doubts, never approve money, so a
  fake has to fool both."
- Handover: "And when the AI is unsure, people take over."

### Slide 8, people (Speaker 3, 3:13–3:44)
- [0–20 s, review desk] "This is the review desk, where the AI hands cases over: why it stopped, the
  facts in dispute, and a Tencent ADP assistant for policy. Why do we need it? Automation fails on
  the hard cases: safety, fakes, large amounts. Without a desk they get a wrong ruling or start
  again from zero. Here the reviewer starts with the evidence already gathered."
- [20–29 s, status page] "Riders and drivers follow their case on a status page, in four languages,
  with one appeal when the AI was unsure. Nobody is left guessing."

### Slide 9, proof and next step (Speaker 3, 3:44–4:05)
"Tested on cases it never saw: the organisers' samples three of three, a blind set 25 of 30, our
regression 45 of 52. And it is ready: one setting connects Ryde's API in shadow mode, ruling beside
your team and paying nothing, at under two cents a dispute. RydeResolve: fair rulings in minutes,
not days. Thank you."

## Q&A (1 minute: two questions at most, 20–25 s per answer)

Speaker 3 takes the question and passes it on.

| Question | Who | Answer (short) |
|---|---|---|
| What if the AI is wrong? | 2 | Money moves only when code has checked the facts and amount against a record; otherwise a person decides. Honest: on our 52-case regression a few automatic rulings were wrong in one re-run. The code judge catches a faulty record only when the Judge lists it, so the next fix checks the record itself. Every miss is published in the repo. |
| Does the photo check work on real fraud? | 2 | Two layers. Code checks the photo's time, place, edit tags and re-use, and that part cannot be talked round. The vision model can only add doubt, never approve money, so a missed fake still needs the time and place to fit. On our photo test sets: 8 of 12 and 9 of 10. |
| Why can't everyone appeal? | 2 | The losing side almost always would, and that undoes automation. Appeals are for rulings under 80% confidence, once, with new evidence; the AI re-checks first. Safety cases never need an appeal: they go to a person from the start. |
| How does it connect to Ryde? | 1 | One client reads Ryde's API and maps it to the organisers' format. It runs in shadow mode: rules next to a person, pays nothing. The field map is our guess until we see Ryde's field list. |
| Where do the policy rules come from? | 1 | Ryde's published policies. Honest: the demo uses our paraphrase, with gaps marked; the official-text version is on a separate branch. Every ruling cites its section. |
| Privacy? | 3 | Demo data only. A deployment masks names, phones and plates before any external model call, or runs the model in-house. The status page shows parties no AI internals. |
| Why Tencent Cloud? | 1 | Lighthouse server in Singapore, the policy assistant on Tencent ADP (Hunyuan), built with CodeBuddy. |
| Does it learn? | 2 | Only through people: a reviewer's decision becomes a precedent after an evaluation gate shows results do not get worse. |

## If something goes wrong
- A clip does not play: click once on the video (it starts), keep talking.
- The deck will not open: play `clips/v4_*.mp4` and `clips/demo4_people_review_status.mp4` in order
  from a file window.
- Do not open the live site on stage unless all of the above fail; if you do, replays only, never
  "Run agents".

## Re-recording the clips
The clips were recorded from the live site with a Playwright script (1440×810, red rings on
clicks, red boxes on the lines we talk about), replays only. The HR-03 replay was imported on the
server from the D66 evaluation trace with `scripts/import_demo_traces.py` (it is `demo-1-HR-03.json`
in "Replay a saved run"). Re-record after any UI change to the dashboard, then rebuild the deck.
