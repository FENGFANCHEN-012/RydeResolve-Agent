# Precedent training set (PT-01 .. PT-10)

## Provenance

Written on 2026-10-13 by a Claude Sonnet subagent, blind. Inputs read, and nothing else:
`data/eval_cases/focus_precedent.txt` (the brief), `data/mock_disputes/README.md`, the format examples
`data/mock_disputes/no_show_01.json` and `data/eval_cases/heldout/DR-002.json`, and `data/policies/official/*.md`.
No source code, tests, scripts, docs, other eval_cases folders or git history were read. All people, trips,
amounts and records are synthetic. Every case carries `expected_outcome.heldout: true`.

These are grey-area past cases a careful reviewer can decide from the records and the case's own policy block. None involves a safety, harassment or fraud allegation.

## Cases

| id | dispute type | filed_by | scenario |
|---|---|---|---|
| PT-01 | no_show | rider | Rider says he was only briefly late for pickup and disputes the no-show fee. |
| PT-02 | cancellation_refund | rider | Rider cancels an advance booking while the driver's phone lost GPS and disputes the fee. |
| PT-03 | fare_dispute | rider | Rider, first complaint ever, objects to a mid-trip stop at a petrol kiosk. |
| PT-04 | route_deviation | rider | Rider claims a long route and leans on the driver's rating and history. |
| PT-05 | cleaning_fee | driver | Driver claims cleaning cost for a spilled drink; some photos failed to upload. |
| PT-06 | no_show | driver | Driver asks for a held no-show fee; the GPS export looks hours off the app log. |
| PT-07 | service_quality | rider | Rider asks for half the fare back, saying the air-con never worked. |
| PT-08 | fare_dispute | driver | Driver asks for the rider's ERP share after a GPS loss in a tunnel. |
| PT-09 | cancellation_refund | rider | Rider cancels an advance booking after a late driver and does not understand a timer value. |
| PT-10 | driver_rights | driver | Driver asks for a waiting fee after a rider took a few minutes to board. |
