# Agent Autonomy Plan: Fixed Procedure, Free Reasoning

> Status: **agreed direction, not built** (2026-10-07). Next improvement after the advocate
> auto-query work (CodeBuddy, `src/agents/query_planner.py`, `src/core/evidence_pool.py`).
> Related: [08_DESIGN_DECISIONS.md](08_DESIGN_DECISIONS.md), [09_FRAUD_AGENT_DESIGN.md](09_FRAUD_AGENT_DESIGN.md).

## 1. The question

Dispute resolution needs a fixed procedure: evidence, classification, case brief, risk check,
debate, ruling, audit, execution. Skipping the audit can pay out the wrong money (NS-002-B1: the
Judge kept a fee it should not have, and only the Fairness check stopped it). A changing order
also produces the inconsistent rulings the brief asks us to remove (handbook p.22). So how does
the system show real agent autonomy?

## 2. The principle

**Fixed procedure, free reasoning.** A court has a fixed procedure (filing, evidence, argument,
judgment, appeal), yet lawyers choose what to investigate and how to rebut, and judges can order
further inquiry or send a case back. Autonomy lives inside each role, not in the order of roles.

- Code owns what must always happen: safety cases go to a person, every ruling is audited before
  it is executed, high fraud risk goes to a person, budgets and step limits hold.
- Agents own what needs judgement: what to look up, when the evidence is enough, what to
  challenge, whether a fact needs more inquiry.
- Every autonomous action is bounded (budget, step limit), grounded (cites evidence-pool ids that
  code checks) and visible (recorded in the live trace and shown in the UI).

## 3. Where agents get freedom (in priority order)

### 3.1 Advocates: autonomous investigation and cross-examination (priority 1)

The handbook's MVP requirement: advocates "autonomously gather their respective evidence" (p.23).

- **Autonomy levels**, chosen per case by a code router (`src/core/autonomy.py`, no model call):
  - L0, rules only: `query_planner` lookups by dispute type and case-brief findings (zero tokens).
  - L1, one decision: after L0 the model decides once whether more lookups are needed
    (`{"needs_more": bool, "queries": [...]}`, at most 2, tools on an allow-list, parameters
    validated by code).
  - L2, bounded loop: look up, think, look up again. Stops when the agent says the evidence is
    enough, the token budget is spent, a query repeats, a lookup returns nothing new, or the
    agent's stance and confidence are unchanged twice (more evidence would not change its mind).
  - Router inputs: contradicting records, data gaps, amount at stake, fraud risk MEDIUM,
    dispute type. Reasons are recorded and shown ("L2: records contradict, amount above S$30").
    `AUTONOMY_LEVEL=0|1|2` forces a level for experiments.
- **Dynamic upgrade:** if the opening statements contradict each other on a fact the pool cannot
  settle, the rebuttal round runs at L2 for that fact.
- **Grounded arguments:** every claim cites evidence-pool ids; code verifies the ids exist (the
  same idea as the fraud labeller's verified quotes, D21).
- **Contested-facts list:** the debate outputs which facts both sides accept and which are
  disputed, with each side's evidence. The Judge rules on the disputed facts one by one.

### 3.2 The Judge can remand for further inquiry (priority 2)

Agent-initiated control flow inside the fixed procedure. When a deciding fact lacks evidence, the
Judge may send the case back to the debate with a named question ("when did the driver reach the
pickup?"). Whether and why to remand is the Judge's decision; code allows **at most one** remand.

### 3.3 Fairness can return a ruling for correction (priority 3)

Today every Fairness finding of high severity sends the case to a person. Split it:
- minor, fixable findings (e.g. a relevant clause not addressed in the reasoning): return the
  ruling to the Judge with the specific issue, **at most once** (a bounded self-correction loop);
- serious findings (fee without basis, refund beyond the disputed amount, safety alert, high
  fraud risk, decisive evidence gap): a person decides, as now.

This should raise the automatic-resolution rate (the brief's goal) without weakening safety.

### 3.4 Asking the parties for evidence (priority 5, if time allows)

When a decisive item is missing (e.g. a cleaning receipt without a shop name), an advocate drafts
a request to the party; the case pauses and resumes when the item arrives.

## 4. Evidence that the design is right

- **LLM-orchestrator experiment** (branch `experiment/llm-orchestrator`, run started 2026-10-07):
  the same nodes with an LLM supervisor choosing every next step, against the fixed pipeline,
  10 cases x 2 repeats each. Measured: verdict accuracy, consistency across repeats, rulings
  executed without an audit or against one, safety cases executed, steps, tokens, cost
  (`scripts/analyze_orchestration.py`). Results to be recorded as a D-entry.
- **Autonomy-level comparison:** the same cases at forced L0, L1, L2 and auto. Report verdict
  accuracy, decisive-evidence recall (answer keys gain a field naming the lookup that settles the
  case), tokens and latency, and plot accuracy against cost per case. Target: auto close to L2's
  accuracy at close to L1's cost. Estimated US$1.5-2.5 on Cerebras; estimate exactly and confirm
  before running.
- Every change runs the regression eval; a change that lowers accuracy is not kept.

## 5. How to present it

> "Autonomy is allocated by risk: simple cases use rules and cost almost nothing, complex cases
> give the agents more freedom, and every autonomous step has a budget, cites its evidence and
> can be checked by code. We tested letting the LLM run the whole pipeline; the data shows which
> decisions can be left to AI and which must stay in code."

Scoring dimensions this answers: AI Interaction, Technical Execution, Feasibility, Innovation,
Responsible AI & Ethics. Demo: one contested case end to end, showing the autonomy level and its
reasons, each advocate's own lookups, the cross-examination, a Judge remand if it happens, the
Fairness check, and the tokens and seconds the case used.

## 6. Order of work

1. Finish and commit the advocate auto-query work (L0/L1) on its own branch; move the five
   complex cases SL-11..SL-15 out of `data/eval_cases/sealed/` (they were run while tuning, so
   they are no longer sealed). Run the regression eval.
2. Add L2, the router, evidence-id checks and the contested-facts list. Eval.
3. Judge remand (one at most). Eval.
4. Fairness return-for-correction (one at most). Eval.
5. Autonomy-level comparison and the accuracy/cost chart.
6. Asking the parties, if time allows.

Build these in CodeBuddy where possible and keep screenshots for the usage proof
(`proof of usage of codebuddy/`).
