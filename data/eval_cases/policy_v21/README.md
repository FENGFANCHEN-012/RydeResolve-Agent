# Policy v2.1 blind test set (V2-01 .. V2-12)

Written 2026-10-14 by a Claude Sonnet subagent, blind. Files read: `data/eval_cases/focus_policy_v21.txt` (the brief), `data/policies/governing/ryde_dispute_resolution_policy_v2_1.md` (the policy) and the three files in `data/Dispute_format/` (format only). No source code, docs, other eval case folders, eval results, answer keys or git history were read.

Each case is plain JSON in the organisers' sample format, with the answer only in `expected_outcome`. Every case carries `_generated_by` and `_role`. Arithmetic (fare breakdowns, excess fare = excess km x rate, surge differentials), wait and contact times against the cancellation time, incident windows against the trip window, and the S$10 / S$50 thresholds were asserted by the generating script, and all 12 files were re-parsed as JSON.

| id | filed_by | scenario |
|---|---|---|
| V2-01 | rider | Rider disputes a S$5.00 no-show fee on a morning booking at Sengkang MRT |
| V2-02 | rider | Rider disputes the extra distance on an evening trip from ION Orchard to JEM |
| V2-03 | rider | Rider disputes a higher fare than the quote on a late-night ride from VivoCity |
| V2-04 | rider | Rider disputes a large fare difference on a post-concert ride from the Indoor Stadium to T3 |
| V2-05 | rider | Rider disputes a S$5.00 no-show fee at Clarke Quay Central |
| V2-06 | rider | Rider disputes the route on an afternoon trip from Bishan to Gardens by the Bay |
| V2-07 | driver | Driver claims S$40.00 for cleaning after a late-night trip to Bedok Reservoir |
| V2-08 | rider | Rider disputes a higher fare than the quote on a trip from Tampines Mall to Singapore Expo |
| V2-09 | rider | Rider asks about a fare difference after an argument with the driver on a trip to Jurong West |
| V2-10 | rider | Rider disputes the route on a morning trip from Punggol to Raffles Place |
| V2-11 | rider | Rider disputes a S$5.00 no-show fee on a Bishan to Mount Elizabeth booking |
| V2-12 | rider | Rider disputes a S$30.00 cleaning fee after a ride from Great World |
