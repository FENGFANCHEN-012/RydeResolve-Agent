# Fresh test set 2 (Sonnet, blind): F2-01 .. F2-20

Written by a Claude Sonnet subagent on 2026-10-12 as a blind test set. The author did not read any
code, tests, scripts, docs or other eval data, and did not see how the system works.

Inputs used (only these): `data/eval_cases/focus_fresh2.txt` (the brief), `data/mock_disputes/README.md`
(labelling conventions), the format examples `data/mock_disputes/no_show_01.json` and
`data/eval_cases/heldout/DR-002.json`, and the official policy text in `data/policies/official/`.

- Dispute ids: F2-01 .. F2-20. Trip ids: RYDE-F2-001 .. RYDE-F2-020.
- Every file carries `"_generated_by"` and `expected_outcome.heldout: true`.
- All amounts are SGD, places are in Singapore, dates are in October 2026, times are +08:00.
- Each case is meant to be solvable from its own records and its own policy block.

| id | dispute type | filed_by | scenario |
|---|---|---|---|
| F2-01 | no_show | rider | Rider charged a no-show fee after a pickup at Tampines Mall; says she came down within minutes |
| F2-02 | no_show | rider | Rider charged a no-show fee after a pickup at ION Orchard; says the driver cancelled too early |
| F2-03 | no_show | rider | Rider charged a no-show fee at Jurong East MRT; says she had messaged she was two minutes away |
| F2-04 | cancellation_refund | rider | Rider cancelled an advance booking for 6pm and was charged a fee; cites an MRT breakdown |
| F2-05 | cancellation_refund | rider | Rider cancelled an on-demand ride at Bishan after a long wait and was charged a fee |
| F2-06 | fare_dispute | rider | Rider charged more than the upfront fare quoted on a Clementi to Marina Bay trip |
| F2-07 | fare_dispute | rider | Rider charged more than the quoted fare on a trip from Tanjong Pagar to Novena through the CBD |
| F2-08 | fare_dispute | rider | Rider billed fare plus several ERP charges on a Woodlands to Orchard trip and disputes them |
| F2-09 | route_deviation | rider | Rider says the driver took a much longer route from Changi City Point to Ang Mo Kio |
| F2-10 | route_deviation | rider | Rider on a metered RydeTAXI trip from Vivocity to Sembawang says the driver left the navigated route |
| F2-11 | service_quality | rider | Rider says the driver stopped for a long time at a petrol station during a Thomson to Bugis trip |
| F2-12 | cleaning_fee | driver | Driver claims a cleaning cost against a rider after a spill on a Holland Village to Bedok trip |
| F2-13 | cleaning_fee | rider | Rider disputes a cleaning fee charged after a Paya Lebar to HarbourFront trip |
| F2-14 | driver_rights | driver | Driver claims a waiting fee after a short Holland Village to Dover pickup |
| F2-15 | driver_rights | driver | Driver claims compensation after a rider cancelled seven minutes after matching |
| F2-16 | no_show | rider | Rider charged a no-show fee at Bedok Mall; says no car ever came |
| F2-17 | cancellation_refund | rider | Rider cancelled a Sengkang pickup after a long wait and was charged a fee |
| F2-18 | cleaning_fee | driver | Driver claims a cleaning cost for a drink spill after a Sengkang to Paya Lebar trip |
| F2-19 | service_quality | rider | Rider ended a late-night trip early and complains about the driver's conduct, asks for the fare back |
| F2-20 | fare_dispute | rider | Rider on a metered RydeTAXI trip to Changi Airport T3 disputes a much higher final fare |
