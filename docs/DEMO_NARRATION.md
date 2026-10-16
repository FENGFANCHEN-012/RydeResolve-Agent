# Demo narration (teleprompter, about 7 min 50 s)

Read-aloud text for the video. Screen cues are in [brackets]; the full walkthrough with setup is in
`docs/DEMO_SCRIPT.md`. About 130 words a minute.

---

**[Cover image, then the architecture figure]**

Ride-hailing platforms handle thousands of disputes a day: a longer route, a no-show fee, a cleaning
charge, an unsafe driver. Today a person reads the GPS trace, the chat, the receipt and the policy for
every one. That takes 24 to 72 hours, and two agents can rule differently on the same facts.

RydeResolve is a team of AI agents that settles these disputes in about a minute and a half. A rider
advocate and a driver advocate each build their side's case from the platform records and Ryde's
policy. A judge weighs both and rules under the organisers' Dispute Resolution Policy, with a confidence score
and its reasons. Photos are checked too. And then code, not the model, checks the ruling before any
money moves, and applies the policy's rules on what must go to a person.

Our rule is simple: if the system cannot prove its ruling from the records, a person decides.

**[Dashboard. Saved runs: demo-7-DISP-001]**

This is the organisers' own sample. A rider going to Changi says the driver took a much longer route
without explaining why. The evidence collector reads the records: four point three kilometres over the
recommended PIE route, and the fare breakdown prices that extra distance at three dollars forty-four.
It also finds a vehicle fire on the PIE during the trip, right on the recommended route.

**[Debate panel, then Judge]**

So the reroute was justified, but the rider asked at 13:24 and the driver never explained. Policy v2.1
says exactly what that means: refund the excess distance fare, not the tolls or the time. The judge
rules three dollars forty-four, citing sections 1.2 and 1.3. Code checks the facts and the amount,
and the policy gate confirms an AI may decide this one. Done, with no human.

**[Scroll to "Sent to both parties"; click 中文, then Melayu]**

Both sides are told the outcome in plain words. Code writes each notice from the ruling itself, so
it can never promise money the ruling did not give, and each party can read it in any of
Singapore's four official languages.

**[Saved runs: demo-6-DISP-003]**

Their surge sample: the surge rose to one point five before pickup, and the log says the rider was
never told. Four dollars fifty, all of it surge, refunded under section 3.3.

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
model check itself. We found this loophole in our sealed test set and added this check; here it stopped
the payout on a fresh set nobody had seen.

**[Review desk]**

The reviewer gets the whole case: the evidence, both arguments, the draft and the exact reason it was
stopped. A reviewer's decision can become a precedent, but only after an evaluation shows it does no
harm.

**[Saved runs: demo-4-IM-04]**

Cleaning fees come with photos, so we check photos twice. Here a driver claims forty dollars for muddy
shoes. Code reads the photo's own data: taken five minutes after drop-off, thirty metres from the
drop-off point, no editing tag, and the same file appears in no other case. A vision model looks at
it: muddy sneakers on the floor mat, matching the claim. The fee stands.

**[Saved runs: demo-5-IM-12]**

This driver claims seventy dollars for a seat stain. The time and place look right. But the vision
model sees a clean seat, and the watermark of an AI image generator. The case goes to a person. The
vision model can only raise doubts; it never approves money. And a doubted photo always goes to a
person, whichever side it would favour.

**[Copy & edit on IM-04]**

You can try this yourself. I copy the genuine case, move the photo's time to half an hour before the
pickup, and save it as a new case. Run it: the collector flags a photo taken before the trip began,
and the rider is not charged: no payment can rest on a doubtful photo. Anyone can build a case here, with the
trip, both profiles, both sides' chat, the rules and the photos, and watch every agent work on it.

**[Saved runs: demo-3-SI-001]**

Last: "The driver kept commenting on my body and said he knows where I stay. I feel unsafe." The
safety scan marks it top priority in under a second, and it goes straight to a person. No debate, no
automatic refund. Safety is never automated.

**[README results table]**

How do we know it works? We test on cases with known answers, including sets written by another model
that never saw our code. Under the organisers' policy, all three of their samples are right. On a blind
set of thirty cases in their full format, twenty-five are right. And fifty-two earlier cases, re-run
under the new policy: forty-four right, then forty-five on our final code. Seventy-eight percent of the
disputes the policy lets AI decide closed with no human, in about ninety seconds each. Most misses are
cases handed to a person, which costs time, not money. But not all: on the final re-run, a few cases
with a broken record were still paid automatically, because the code judge only caught the broken
record when the model listed it. That is our next fix: check the record itself, in code. The blind set
did catch two wrong payouts; we fixed both and ran the cases again. Every miss, and the fix it led to,
is published in the repo.

**[A CodeBuddy screenshot]**

We built RydeResolve with CodeBuddy. Two habits made the difference. First, ask for a diagnosis and
the cost before building: for fully autonomous agent loops, CodeBuddy laid out the token, latency and
testing cost, and we chose constrained autonomy. Second, commit a baseline before every experiment:
a token-saving change looked good until the A/B test showed it hurt accuracy.

**[Cover image]**

RydeResolve: fair, explainable ride-dispute rulings in minutes, not days.
