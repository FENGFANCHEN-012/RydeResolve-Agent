# Photo-side blind test set (PS-01 .. PS-10)

Written 2026-10-14 by a Claude Sonnet subagent, blind. Files read: `data/eval_cases/focus_photo_side.txt` (the brief),
`data/evidence_samples/library/README.md`, `data/mock_disputes/README.md`, `data/mock_disputes/cleaning_fee_01.json`,
`data/eval_cases/heldout/DR-002.json` (format examples) and `data/policies/official/*.md` (only the cleaning-fee passages).
No source code, docs, other eval sets, results or git history were opened, and no image was viewed.
Photo times and distances were computed with a script (haversine) when the files were generated.

| id | filed_by | scenario | where the scenario does NOT reveal the photo problem |
|---|---|---|---|
| PS-01 | rider | Muddy-floor fee S$90, no receipt; photo taken 18 min after drop-off | Title, ticket text and caption say nothing about place; the problem is only the photo GPS, about 3.0 km from the drop-off |
| PS-02 | rider | Genuine mud photo 14 min after drop-off, about 120 m away, receipt S$80; rider argues "just dust" | Nothing to hide; fee stands. The same photo is reused later in PS-09 |
| PS-03 | rider | Mud fee S$150 (above stain tier), no receipt; photo captured 07:41, pickup 09:15 | Ticket and caption say "after the passenger left"; only the capture time (before pickup) shows the problem |
| PS-04 | rider | Vomit fee S$180 with receipt; photo time and GPS fine | Metadata and receipt look clean; the problem is the image content (empty seat, "pollinations.ai" watermark) |
| PS-05 | rider | Photo has no capture time or GPS; rider admitted clay on the mat in chat at 13:55, receipt S$70 matches | The missing metadata looks suspicious but is not the issue; the chat admission and receipt settle it (fee stands) |
| PS-06 | driver | Driver claims S$65 for a dirty carpet; photo 25 min after drop-off, about 100 m away, receipt, rider acknowledged in chat | Nothing hidden; claim upheld, S$65 awarded |
| PS-07 | rider | Mud fee S$85 with receipt; photo time and GPS fine | Time, place and receipt look fine; only the software field ("Adobe Photoshop") is wrong |
| PS-08 | rider | Vomit fee S$160, no receipt; photo 22 min after drop-off, near drop-off | Caption says the driver already cleaned it; only the photo content (clean white leather seats, no mess) shows the problem |
| PS-09 | driver | Driver claim S$75 with receipt for a 13 Oct trip; rider says shoes were clean | The photo is a byte-for-byte copy of PS-02 photo1.jpg (same driver, 5 Oct trip); the ticket and caption describe it as fresh |
| PS-10 | rider | Genuine mud photo 38 min after drop-off, about 170 m away, S$60 within stain tier, no receipt; rider argues rain | Missing receipt looks like a weakness but the amount is a standard tier; fee stands |
