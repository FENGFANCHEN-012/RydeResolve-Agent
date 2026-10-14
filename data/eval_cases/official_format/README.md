# Official-format test set OF-01 .. OF-30

Generated 2026-10-14 by a Claude Sonnet subagent, blind. Brief: `data/eval_cases/focus_official_format.txt`.

## How it was written

The author read only these files and no source code, docs, other eval case folders, eval results, answer keys or git history:

- `data/eval_cases/focus_official_format.txt` (the brief)
- `data/policies/governing/ryde_dispute_resolution_policy_v2_1.md` (the policy)
- the three files in `data/Dispute_format/` (DISP-001, DISP-002, DISP-003; format only)
- `data/evidence_samples/library/README.md` (what each library photo shows)

Each case follows the DISP record format (ticket, profiles, trip_data, GPS, chat, app events and the record
sections the case needs) with the answer only in `expected_outcome`. Each case also carries `_generated_by` and
`_role`. Fare sums, excess fare = excess km x rate, surge differentials, wait and contact times relative to the
cancellation, incident windows vs the trip window, photo times vs drop-off (24 h rule) and the S$10 / S$50 bands
were checked by script before writing. Photo cases carry `_photo_stamps` for the stamping script; photo files are
not created here.

## Cases

| id | filed_by | scenario |
|---|---|---|
| OF-01 | rider | Rider disputes a fare higher than the quote on a short city trip |
| OF-02 | rider | Rider disputes the distance charged on an evening trip from Ang Mo Kio |
| OF-03 | rider | Rider disputes a S$5.00 cancellation fee at an MRT pickup |
| OF-04 | rider | Rider disputes the distance charged on a lunchtime trip from Bedok to Orchard |
| OF-05 | rider | Rider disputes a cleaning fee after a morning trip from a nature reserve |
| OF-06 | rider | Rider asks for a full refund of a short trip after a complaint about the ride |
| OF-07 | rider | Rider disputes the distance charged on a morning trip from Jurong East |
| OF-08 | rider | Rider disputes the distance charged on a trip from Holland Village |
| OF-09 | rider | Rider disputes the price of a morning trip to Changi Business Park |
| OF-10 | rider | Rider disputes a S$5.00 fee at a Sengkang mall pickup |
| OF-11 | rider | Rider disputes a fare higher than the quote on a peak-hour trip |
| OF-12 | driver | Driver asks for payment for a wait at a Hougang pickup |
| OF-13 | rider | Rider disputes a fare higher than the quote on an evening trip |
| OF-14 | rider | Rider disputes the fare against the quote on a late-evening trip |
| OF-15 | rider | Rider disputes a S$5.00 fee at an Orchard pickup |
| OF-16 | rider | Rider complains about how the driver handled a morning trip to Tampines |
| OF-17 | driver | Driver claims a cleaning fee after an evening trip from Kallang |
| OF-18 | rider | Rider complains about a late-night trip to Woodlands |
| OF-19 | driver | Driver claims a cleaning fee after a night trip from Pasir Ris |
| OF-20 | rider | Rider disputes the price of a late-night airport trip |
| OF-21 | rider | Rider disputes a fare higher than the quote on a Tampines to Raffles Place commute |
| OF-22 | rider | Rider disputes a S$5.00 fee at Holland Village |
| OF-23 | driver | Driver claims a cleaning fee after an evening trip from MacRitchie |
| OF-24 | rider | Rider complains about a morning booking from Bishan |
| OF-25 | rider | Rider disputes the distance charged on an afternoon trip from Punggol |
| OF-26 | rider | Rider disputes the price of a late-evening trip from VivoCity |
| OF-27 | driver | Driver claims for damage to a car after an afternoon trip from Pioneer |
| OF-28 | rider | Rider disputes the distance charged on an evening trip from Woodlands |
| OF-29 | rider | Rider disputes a S$5.00 fee at a Bugis pickup |
| OF-30 | driver | Driver claims a cleaning fee after a late-night trip from Esplanade |
