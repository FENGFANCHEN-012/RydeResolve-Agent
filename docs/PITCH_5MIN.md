# RydeResolve: Demo Day pitch (5 minutes)

Demo Day, 3 Nov 2026, Marina Bay Sands. Five minutes to present and demonstrate. The rehearsal is
2 Nov 16:00. This script is timed for 4 min 45 s spoken, leaving 15 s of slack. The video script
(`DEMO_SCRIPT.md`) is the long form; this one keeps three cases and drops the editor segment.

## Rules for the live demo

- Replays only. Every case below is a saved run under "Replay a saved run" on
  http://43.134.17.192. A replay never calls a model, so quota, latency and a different ruling
  cannot hurt the demo. Do not press "Run agents" on stage.
- Open the site, enter the access code and load the first replay before walking up. Keep the
  review desk (`/review.html`) in a second tab.
- One presenter speaks, one drives the screen. The driver clicks only when the script says "show".
- If the site is down: the same screens are in the demo video; play the clip for the case.

## 0:00-0:40 The problem (slide: one line and one number)

Say:
- "A rider in Singapore gets charged S$8.60 for a trip she says went the long way. She files a
  dispute. Today a person opens the GPS trace, the chat log, the fare breakdown, the policy, and
  decides. It takes one to three days, and two agents can rule differently on the same facts."
- "RydeResolve rules a standard dispute in about two minutes with a team of AI agents. A rider
  advocate, a driver advocate and a judge, with evidence, photo, fraud and fairness checks around
  them. It applies Ryde's own Dispute Resolution Policy section by section."
- "One rule above all: if the system cannot prove its ruling from the records, a person decides."

Show: the architecture figure for 10 s. Point at the flow: records, advocates, judge, code checks.

## 0:40-2:00 Case 1: the organisers' own sample (replay demo-7-DISP-001)

Say: "This is the organisers' route-deviation sample. Orchard Central to Changi Terminal 3. The
rider says the driver took a long route and never told her."

Show each step as it lights up, 15 s each:
1. Collector. "Code reads the records: 24.8 km driven against a 20.5 km recommended route. The fare
   breakdown holds an excess-distance fare of S$3.44. A traffic record shows a vehicle fire on the
   PIE, active during the trip, on the recommended route."
2. Advocates. "The rider's advocate: she asked at 13:24 and got no answer. The driver's advocate:
   the PIE was on fire. Both cite the policy."
3. Judge. "Partially upheld, S$3.44. Section 1.2: notify the rider. Section 1.3: rerouted for
   traffic but not informed, so the excess-distance fare comes back, not the tolls, not the time."
4. Code checks. "Every fact in the ruling is traced to a record. S$3.44 is a record figure. Under
   S$10 and no safety issue, so the ruling is final and executed."

Show: scroll to "Sent to both parties", click 中文, then Melayu (10 s). Say: "Both parties get a
notice built by code from the ruling's fields, in four languages. It cannot state an amount the
ruling did not make, and it tells both of them how to ask for a person."

## 2:00-3:00 Case 2: the code judge stops a wrong refund (replay demo-2-F2-17)

Say: "Now the case we are proudest of, because the system was wrong and caught itself."

Show the chain, 12 s each:
1. "The rider cancelled after 23 minutes and was charged S$5. But the driver-assignment record has
   a logged data problem, and the ETA shown to her is missing."
2. "Judge, first draft: refund S$5, confidence 0.62, resting on that questioned record."
3. "The code judge blocks it and lists the problems."
4. "Judge, second draft: still S$5, confidence now 0.85. It simply dropped the questioned record."
5. "The code judge sees the same payout as the blocked draft. The case goes to a person."

Say: "The model raised its own confidence with no new evidence. That is why code checks the model,
and the model never checks itself."

Show: the review desk tab (10 s). "A reviewer sees why it was stopped, decides, and that decision
can become a precedent only after it passes an evaluation gate."

## 3:00-3:40 Case 3: safety is never automated (replay demo-3-SI-001)

Say: "A rider writes: the driver kept commenting on my body and said he knows where I stay."

Show: the safety scan marks it P0 in under a second. No advocates, no judge. The rider's notice says
a specialist will contact her and no money moves until then.

Say: "Since our submission we hardened this path. Harassment now routes on the message itself, not
on a keyword list alone: a chat model labels an unwanted advance and code checks that label. On
two blind sets written by another model that never saw our code: 10 out of 10 and 6 out of 6.
Every change we made is logged, with what it fixed and what it did not."

## 3:40-4:25 How we know it works, and what it costs

Show: the results table (one slide, keep it on screen while speaking).

Say:
- "The organisers' three samples: 3 of 3. A 30-case blind set in their full format: 25 of 30.
  52 earlier cases under the current policy: 44 of 52, with zero wrong payouts."
- "Most misses are cases handed to a person. That costs minutes, not money. The rest we publish."
- "Each agent sees only what its role needs: the advocates never see fraud scores or a party's
  history, so they argue the case, not the person. Every ruling goes to a hash-chained audit log."
- "Cost: about 1.7 US cents per dispute on an open 120-billion-parameter model. At 1,000 disputes a
  day, about US$500 a month. It can run on a company's own GPU server, so the data never leaves."

## 4:25-4:45 What happens next

Say: "The next step is not more agents. It is real data, and that is already built: one setting
connects Ryde's API in shadow mode. The system reads live disputes, writes its ruling next to the
human one and pays nothing, until the agreement rate earns it the right to decide small cases
alone."

Close: "RydeResolve. Fair, explainable ride-dispute rulings in minutes, not days. Thank you."

## Likely questions (30-second answers)

- **What if the model is wrong?** Money moves only when code can verify every fact and amount
  against a record. If not, a person decides. In our 52-case run that gave zero wrong payouts.
- **Why two advocates?** A single model asked "who is right" anchors on the complaint. Two
  advocates make it find the evidence for each side first, and the judge rules on evidence it can
  cite.
- **How does it connect to Ryde?** One client class (`src/integrations/ryde_api.py`) reads the
  dispute, trip, chat, payments and photos. The demo reads dataset files in the DISP-002 format.
  With `RYDE_API_MODE=http` it reads Ryde's API and maps the fields to that same format, so nothing
  downstream changes. It runs in shadow mode: it rules next to a person and pays nothing. The field
  map is our guess until we see Ryde's real field list.
- **Where do the policy rules come from?** From Ryde's published policies. Honest answer: the demo
  uses our paraphrase, and where the policy was silent we wrote a rule and marked it. A version built
  from the official text is ready on a separate branch. Either way, every ruling cites the section
  it used, so a reviewer can check it.
- **Can the rider or driver disagree?** Yes. Every notice, in four languages, says they can ask for
  a person. The "Ask a person" form sends the case to the review desk, and nothing is paid or
  reversed until a reviewer decides.
- **Does it learn?** Only through people. A reviewer's decision becomes a precedent only after an
  evaluation gate shows results do not get worse. A stronger version of this loop is being tested
  separately and is not in the live demo.
- **Accessibility?** Notices in English, Chinese, Malay and Tamil. The dashboard has a skip link,
  screen-reader status updates, keyboard upload, labelled inputs and 4.6:1 contrast on hint text.
- **Privacy?** Demo data only. A real deployment masks names, phones and plates before any
  external model call, or keeps the model in-house; both parties are told an AI took part and how
  to ask for a person.
- **Why Tencent Cloud?** The app runs on a Tencent Cloud Lighthouse server in Singapore; the policy
  assistant is published on Tencent ADP; the whole project was built with CodeBuddy.
