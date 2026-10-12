# Fresh test set (Sonnet), FS-01 .. FS-20

Made by a Claude Sonnet subagent on 2026-10-12, without reading the system's code, tests or earlier
eval data. Inputs it used: the brief `data/eval_cases/focus_fresh.txt`, the labelling conventions in
`data/mock_disputes/README.md`, the case format of two example files, and the official policy text in
`data/policies/official/`.

- Dispute ids: FS-01 .. FS-20
- Trip ids: RYDE-FS-001 .. RYDE-FS-020
- Files: `FS-01.json` .. `FS-20.json`, each with `"_generated_by"` and `"heldout": true` in `expected_outcome`
- Each case is meant to be solvable from its own records and its own policy block.

| id | dispute type | filed_by | scenario |
|---|---|---|---|
| FS-01 | no_show | rider | Rider disputes a no-show fee; disagrees with the wait length and says driver was rude |
| FS-02 | cancellation_refund | rider | Rider cancelled after matching because of a wrong pickup pin; disputes the cancellation fee |
| FS-03 | fare_dispute | rider | Rider says the fare was higher than the price she remembers; claims no surge was shown |
| FS-04 | driver_rights | driver | Driver wants a bubble-tea spill cleaning fee charged to a rider; took no photos |
| FS-05 | route_deviation | rider | Rider objects to a long detour on a closed-road night and says she was never asked |
| FS-06 | cancellation_refund | rider | Rider cancelled a late driver and says he never contacted her |
| FS-07 | no_show | rider | Rider charged a no-show fee after the driver cancelled following a wait she says was shorter |
| FS-08 | cancellation_refund | rider | Rider cancelled a late driver and was still charged a fee |
| FS-09 | fare_dispute | rider | Rider says her card was charged twice for one short trip |
| FS-10 | driver_rights | driver | Driver says the rider kept him waiting at pickup and no waiting fee was added |
| FS-11 | cleaning_fee | rider | Rider disputes a cleaning fee for a short campus trip and doubts the driver's photos |
| FS-12 | cleaning_fee | rider | Rider admits being sick in the car but disputes the size of the cleaning fee |
| FS-13 | fare_dispute | rider | Rider disputes ERP charges on her receipt |
| FS-14 | cancellation_refund | rider | Rider cancelled an advance booking shortly before pickup and disputes the fee |
| FS-15 | route_deviation | rider | Rider wants a refund after the driver missed an expressway exit |
| FS-16 | no_show | driver | Driver says he waited for a rider at a mall lobby; rider says no car came |
| FS-17 | route_deviation | rider | Rider says the fare rose far above the quote after a long route |
| FS-18 | cleaning_fee | rider | Rider disputes a cleaning fee after an airport trip and doubts the receipt |
| FS-19 | service_quality | rider | Rider reports unwelcome comments in the car and calls afterwards |
| FS-20 | driver_rights | driver | Driver claims repair costs for a damaged seat tray against a rider |
