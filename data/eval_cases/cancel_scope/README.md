# Cancellation-scope blind test set (CS-01 .. CS-10)

Written 2026-10-14 by a Claude Sonnet subagent, blind. Purpose: test who a no-show /
cancellation fee covers when the driver is the one who presses cancel.

## How it was written

The author read only: `data/eval_cases/focus_cancel_scope.txt` (the brief),
`data/mock_disputes/README.md`, one format example (`data/mock_disputes/no_show_02.json`),
`data/eval_cases/heldout/DR-002.json`, and the official policy files under
`data/policies/official/` (only the cancellation / waiting-fee passages were consulted).
No source code, docs, other eval case folders, eval results or git history were read.
Each case carries a `cancellation_policy` block with the exact texts from the brief.
Wait times were computed from `driver_arrival_time` to `cancellation_time` by script and
asserted; the GPS offset in the conflict case was checked with a haversine calculation.

## Cases

| id | filed_by | scenario |
|---|---|---|
| CS-01 | rider | Charged a no-show fee after a morning airport booking from Sengkang; rider says she did not cancel |
| CS-02 | rider | Lunchtime pickup at Holland Village MRT; rider charged and says she came out as the car left |
| CS-03 | rider | Yishun morning pickup to Woodlands; rider charged though she messaged she was coming |
| CS-04 | driver | Tiong Bahru evening pickup; fee is on hold after the rider complained |
| CS-05 | rider | Marine Parade pickup; rider charged a few minutes after the driver arrived |
| CS-06 | rider | Early Bukit Panjang pickup to NUH; rider charged and says she never pressed cancel |
| CS-07 | rider | Marina Bay Sands evening pickup to Sentosa; rider charged although she was at the lobby |
| CS-08 | rider | Tampines Mall pickup; rider charged after a short delay in the mall |
| CS-09 | driver | Jurong East MRT late-night pickup; fee held after the rider objected |
| CS-10 | rider | Bishan park carpark pickup; rider charged and says she never saw the car |
