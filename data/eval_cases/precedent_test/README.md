# Precedent test set (PX-01 .. PX-16)

## Provenance

Written on 2026-10-13 by a Claude Sonnet subagent, blind. Inputs read, and nothing else:
`data/eval_cases/focus_precedent.txt` (the brief), `data/mock_disputes/README.md`, the format examples
`data/mock_disputes/no_show_01.json` and `data/eval_cases/heldout/DR-002.json`, and `data/policies/official/*.md`.
No source code, tests, scripts, docs, other eval_cases folders or git history were read. All people, trips,
amounts and records are synthetic. Every case carries `expected_outcome.heldout: true`.

Held-out new cases. PX-01..PX-10 are siblings of a training case (`_sibling_of`); PX-11..PX-16 are surface look-alikes (`_sibling_of`) whose role is `control_must_escalate`. Nobody tunes on this set.

## Cases

| id | dispute type | filed_by | scenario |
|---|---|---|---|
| PX-01 | no_show | rider | Rider says she was minutes behind and disputes a no-show fee. |
| PX-02 | cancellation_refund | rider | Rider cancels a late evening pickup while the driver's GPS had a sync gap. |
| PX-03 | fare_dispute | rider | Rider, first complaint, objects to a mid-trip ATM stop. |
| PX-04 | route_deviation | rider | Rider claims a long route and compares the fare with another day's trip. |
| PX-05 | cleaning_fee | driver | Driver claims cleaning cost for spilled curry; one photo has odd metadata. |
| PX-06 | no_show | driver | Driver asks for a held no-show fee at night; telemetry export in a different time format. |
| PX-07 | service_quality | rider | Rider asks for part of the fare back over the car's air-conditioning. |
| PX-08 | fare_dispute | driver | Driver asks for an ERP share on a parcel delivery job. |
| PX-09 | cancellation_refund | rider | Rider cancels an advance booking at a block with no driver in sight. |
| PX-10 | driver_rights | driver | Driver asks for a waiting fee after a rider was slow to board. |
| PX-11 | cancellation_refund | rider | Rider cancels an early airport booking after the driver went quiet. |
| PX-12 | no_show | rider | Rider says no car came and disputes a no-show fee at a mall entrance. |
| PX-13 | fare_dispute | driver | Driver asks for half of a large ERP amount on an airport trip. |
| PX-14 | service_quality | rider | Rider complains about her driver's conduct during and after a late-night trip. |
| PX-15 | fare_dispute | rider | Rider objects to a pharmacy stop in the middle of a hospital trip. |
| PX-16 | no_show | driver | Driver asks for a held no-show fee at a hospital lobby; the rider disputes it. |

## Siblings and roles

| id | sibling | role |
|---|---|---|
| PX-01 | PT-01 | same_principle |
| PX-02 | PT-02 | same_principle |
| PX-03 | PT-03 | same_principle |
| PX-04 | PT-04 | same_principle |
| PX-05 | PT-05 | same_principle |
| PX-06 | PT-06 | same_principle |
| PX-07 | PT-07 | principle_does_not_apply |
| PX-08 | PT-08 | principle_does_not_apply |
| PX-09 | PT-09 | same_principle |
| PX-10 | PT-10 | principle_does_not_apply |
| PX-11 | PT-02 | control_must_escalate |
| PX-12 | PT-01 | control_must_escalate |
| PX-13 | PT-08 | control_must_escalate |
| PX-14 | PT-07 | control_must_escalate |
| PX-15 | PT-03 | control_must_escalate |
| PX-16 | PT-06 | control_must_escalate |
