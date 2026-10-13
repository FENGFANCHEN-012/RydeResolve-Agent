# Demo narration (teleprompter, about 7 minutes)

Read-aloud text for the video. Screen cues are in [brackets]; the full walkthrough with setup is in
`docs/DEMO_SCRIPT.md`. About 130 words a minute.

---

**[Cover image, then the architecture figure]**

Ride-hailing platforms handle thousands of disputes a day: a longer route, a no-show fee, a cleaning
charge, an unsafe driver. Today a person reads the GPS trace, the chat, the receipt and the policy for
every one. That takes 24 to 72 hours, and two agents can rule differently on the same facts.

RydeResolve is a team of AI agents that settles these disputes in about a minute and a half. A rider
advocate and a driver advocate each build their side's case from the platform records and Ryde's
policy. A judge weighs both and rules, with a confidence score and its reasons. And then code, not the
model, checks the ruling before any money moves.

Our rule is simple: if the system cannot prove its ruling from the records, a person decides.

**[Dashboard. Saved runs: demo-1-RD-001]**

Here is a rider who says the driver missed the exit on the AYE. The fare was eighteen dollars twenty
instead of the fourteen fifty quoted.

The evidence collector reads the GPS, the fare and the app events with code tools, and every finding
names the record it came from. It finds the route-deviation alert: 10.4 kilometres against 8.2 planned.

**[Debate panel]**

The two advocates argue. Notice the driver's side does not deny it: the driver admitted the missed
exit in the chat.

**[Judge, then Code Judge]**

The judge upholds the claim: a refund of three dollars seventy, confidence 0.92. Now the code judge
checks it. Is every fact the ruling rests on verified, on a record nothing contradicts? Is three
seventy plain arithmetic on figures in the records, eighteen twenty minus fourteen fifty? Yes. The
fairness audit passes, and both rider and driver are told the outcome.

This is the common path. In our blind tests, 82 percent of standard disputes closed like this, with no
human.

**[Saved runs: demo-2-F2-17]**

Now a harder one. A rider cancelled after waiting 23 minutes and was charged five dollars. But the
platform logged a data problem on the record of when the driver was assigned, and the ETA shown at
assignment is missing. Nobody can prove the timeline.

The judge's first draft refunds five dollars, with confidence 0.62. It rests on "cancelled 22.9
minutes after matching", which comes from that broken record. The code judge blocks it and sends it
back.

**[Second draft]**

Look at the second draft. Same five dollars. Confidence now 0.85. No new evidence: the model simply
deleted the broken record from its list of facts. The code judge sees that the ruling pays the same as
the draft it blocked, without the record it rested on, and sends the case to a person.

A model raised its own confidence from 0.62 to 0.85 with nothing new. That is why we never let the
model check itself. We found this loophole in our sealed test set, closed it, and it stopped this
payout on a fresh set nobody had seen.

**[Review desk]**

The reviewer gets the whole case: the evidence, both arguments, the draft and the exact reason it was
stopped. A reviewer's decision can become a precedent, but only after an evaluation shows it does no
harm.

**[Saved runs: demo-3-SI-001]**

Last: "The driver kept commenting on my body and said he knows where I stay. I feel unsafe." The
safety scan marks it top priority in under a second, and it goes straight to a person. No debate, no
automatic refund. Safety is never automated.

**[README results table]**

How do we know it works? We test on cases with known answers, including sets written by another model
that never saw our code, and a sealed set we ran once and never tuned on. 78 of 101 rulings were
correct; most misses were cases handed to a person, which costs time, not money. There were two wrong
payouts, of eight dollars each, and we publish both.

**[A CodeBuddy screenshot]**

We built RydeResolve with CodeBuddy. Two habits made the difference. First, ask for a diagnosis and
the cost before building: when we asked about fully autonomous agent loops, CodeBuddy laid out the
token, latency and testing cost, and we chose constrained autonomy instead. Second, commit a baseline
before every experiment and measure it: a token-saving change looked good until the A/B test showed
it hurt accuracy, so we kept only the safe part.

**[Cover image]**

RydeResolve: fair, explainable ride-dispute rulings in minutes, not days.
