# Project Requirements: Tencent Cloud AI CAN DO IT Hackathon Singapore 2026

Source: the official handbook, "Competition Requirement.pdf" (Ryde track, pages 21-26;
submission, timeline and judging, pages 36-41). Rewritten on 2026-09-30 to match the
handbook word for word where it matters. The earlier version of this file contained
items that are **not** in the handbook; they are listed at the end so nobody relies on them.

## Competition

| Item | Detail |
|---|---|
| Event | AI CAN DO IT Tencent Cloud Hackathon Singapore 2026 (Tencent Cloud + AI Singapore) |
| Track | Digital Native: Ryde |
| Challenge | **Multi-Agent Autonomous Dispute Resolution System** |
| Submission deadline | **16 Oct 2026** |
| Finalists announced | 23 Oct 2026 (top 2 teams per track) |
| Demo Day | 3 Nov 2026 (TBC) |

## Problem statement (handbook p.22)

> Build an autonomous, multi-agent dispute resolution system that can handle complex,
> multi-party conflicts between riders and drivers: gathering evidence, building cases,
> applying company policy, and issuing fair rulings quickly, transparently, and without
> human intervention for the majority of standard dispute categories.

Pain points named by Ryde: high operational cost, 24-72 h resolution time, inconsistent
rulings between human agents, and churn from users who feel unfairly treated.

## 1. MVP (required): three core agents (p.23)

Teams are evaluated **primarily** on this. Agents work on text and structured data.

| Agent | Role | Required capabilities |
|---|---|---|
| Rider Advocate | Represents the rider | Gathers rider-side evidence, argues the rider's claim based on company policy |
| Driver Advocate | Represents the driver | Gathers driver-side evidence, argues the driver's defence based on policy |
| Judge | Impartial arbitrator | Weighs both cases, applies policy, rules (refund, compensation, no action), explains its reasoning |

**Evidence sources:** GPS and telemetry (route vs optimal route, unexpected stops,
duration vs estimate); chat logs (sentiment, agreements, disagreements, threats);
payment and fare data (fare breakdown, surge pricing, promo codes); historical behaviour
profiles (dispute history, rating patterns, account age).

**Workflow:**
1. A dispute is filed.
2. The Rider and Driver Advocates **autonomously gather their respective evidence** from
   the available data sources.
3. Each advocate builds and presents its case, **citing relevant company policy**.
4. The Judge reviews both cases, applies policy, and issues a ruling with a
   **confidence score** and a natural-language reasoning summary.
5. The system outputs the ruling, the recommended action (e.g. "partial refund of $3.25")
   and the explanation **to both parties**.

## 2. Stretch goals (bonus points) (p.24)

| Capability | What the handbook asks for |
|---|---|
| Evidence Collection Agent | Orchestrates multi-modal data retrieval across tools and APIs; feeds structured evidence to the advocates |
| Fraud & Bad-Faith Detection Agent | Runs in parallel; flags dispute abuse, fake claims, collusion; feeds risk signals to the Judge |
| Policy & Precedent Agent | Keeps a knowledge base of policies **and past rulings**; gives the Judge precedent-based recommendations (e.g. RAG) |
| Image Analysis (multi-modal) | Checks mess/damage photos: genuine, matches trip time, not AI-generated |
| Escalation Protocol | Judge confidence below a threshold -> escalate to a human with a full case summary |
| Learning Feedback Loop | Human overrides are fed back into the Policy & Precedent knowledge base |
| SLA & Routing Manager | Prioritises by urgency and value; safety cases fast-tracked |

## 3. Guardrails (p.25)

- Stretch goals only after the MVP is fully functional.
- Mock external APIs where needed; a sample dataset is provided (DISP-002 format).
- Any LLM or agent framework may be used.
- **Demoable end to end for at least two dispute categories** by Demo Day.
- **Inter-agent communication must be observable** (e.g. a visible log or UI).
- Sample categories: route deviation, no-show charge, property damage / mess (needs image
  analysis, a stretch goal), safety incident.

**Must include (p.26):** working prototype (2+ categories), architecture diagram,
live demo walkthrough, source code on GitHub.

## Submission (p.37)

- **The project must be built on CodeBuddy or WorkBuddy, with proof of use** (chat
  screenshots, API logs or a written development description). Without proof the project
  is not scored.

| Item | Required? | Notes |
|---|---|---|
| Project title | Required | |
| Short blurb | Required | **Under 10 words** |
| Project description | Required | Overview (scenarios, users, value); real-world pain points; business and technical architecture **and how prompts drive the AI**; business value with quantified metrics |
| CodeBuddy / WorkBuddy conversation history | Required | At least 3 screenshots or a screen recording |
| Cover image | Required | 16:9, recommended 380x216 px |
| Demo video | Optional | 5-8 min: overview, core agent features, reflection on the build and CodeBuddy/WorkBuddy tips |
| Project link | Optional | Live URL **earns bonus points** |

Suggested (not required) Tencent tools: WorkBuddy, CodeBuddy, ADP, Miora, Agent Runtime,
TRTC ASR/TTS, and Tencent Cloud infrastructure.

## Judging (p.40)

- **Preliminary:** judged by Ryde and Tencent Cloud experts. Detailed track criteria are
  "shared with participants after registration". **Action: check whether we received them.**
- **Demo Day:** ten dimensions, 10 points each: Impact & Relevance, Human-Centered Design,
  AI Interaction, Technical Execution, Feasibility, Demo & Storytelling, Innovation &
  Creativity, UX & Accessibility, **Responsible AI & Ethics**, Overall Quality.

## Where we stand (2026-09-30)

| Requirement | Status | Where |
|---|---|---|
| Rider / Driver Advocates | Done | `src/agents/passenger.py`, `driver.py` |
| Advocates *autonomously gather* their evidence | **Partial**: they receive the case data and one shared policy search; they cannot run their own lookups | see `08_DESIGN_DECISIONS.md` D7 |
| Judge with confidence and reasoning | Done | `src/agents/arbitrator.py` |
| Evidence sources (GPS, chat, fare, profiles) | Done (mock data) | `data/mock_disputes/` |
| 2+ categories end to end | Done: no-show, cancellation, route, fare, mess, safety, service | 14-case eval, 86% verdict accuracy |
| Observable inter-agent communication | Done | live agent trace in the dashboard |
| Evidence Collection Agent | **Partial**: deterministic Collector with tools; not multi-modal | `src/agents/collector.py` |
| Policy & Precedent Agent | **Partial**: official-policy RAG; **no past rulings yet** | `src/agents/policy.py` |
| Escalation Protocol | Done: confidence threshold plus Fairness checks route to human review | `src/core/workflow.py`, `fairness.py` |
| SLA & Routing | Partial: urgency tiers, safety cases go straight to a human; no queue | `classifier.py` |
| Fraud & Bad-Faith Agent | Not built (profiles carry fraud flags only) | |
| Image Analysis | Not built (photos are text descriptions) | |
| Learning Feedback Loop | Not built | |
| CodeBuddy proof | In progress | `proof of usage of codebuddy/` |
| Blurb, cover image, description | To do | |

## Corrections to the previous version of this file

These were in the old file but are **not** in the handbook:

- "Support Singapore's four official languages": not required anywhere.
- Scoring weights (Innovation 25%, Technical 25%, Business 20%, Demo 20%, Completeness 10%):
  not in the handbook. The real Demo Day rubric is the ten equal dimensions above.
- "Demo video 3-5 minutes, required" and "PPT required": the video is **optional, 5-8 min**;
  a PPT is not listed.
- The seven scenarios: the handbook lists four sample categories; fare disputes appear
  as an evidence source, and cancellation refund and service quality are our own additions.
- The handbook requires no dedicated RAG agent in the MVP. Advocates must cite policy;
  RAG appears in the stretch goal "Policy & Precedent Agent", whose job includes
  **past rulings** as well as policies.
