# Ryde Platform Policy Documents

This directory contains real Ryde policy documents sourced from the official Ryde website and help center, used for RAG indexing.

## Document Index

| # | File | Source | Description |
|---|------|--------|-------------|
| 1 | `terms_of_use.md` | https://rydesharing.com/terms-of-use/ | Full Terms of Use (last modified: 6 April 2022) — definitions, user/driver obligations, payments, platform rules, liability, dispute resolution, Singapore-specific regulations |
| 2 | `cancellation_policy.md` | Ryde Help Center | Cancellation and Waiting Time Policy — fee structure, grace periods, driver/rider cancellation rules, dispute process |
| 3 | `refund_policy.md` | Ryde Terms of Use | Refund Policy — eligibility, non-refundable items, cleaning fees, RydeCoins terms, processing timeline |
| 4 | `driver_guidelines.md` | Ryde Code of Conduct + Blog posts | Driver guidelines — Code of Conduct (4 rules), safe driving tips, platform work safety and fairness, 0% commission model |
| 5 | `safety_standards.md` | Ryde Terms of Use + Code of Conduct + Blog posts | Safety standards — incident classification (P0-P3), GPS monitoring, screening, insurance, in-vehicle recording |
| 6 | `rider_code_of_conduct.md` | https://rydesharing.com/code-of-conduct/ | Code of Conduct — 4 Simple Rules to a Better Ride (Safety First, Be Punctual, Communicate, Mutual Respect) |
| 7 | `driver_performance_standards.md` | Ryde Help Center | Driver Performance and Community Standards — ratings, cancellation rate, acceptance rate, account suspension/reinstatement |
| 8 | `privacy_policy.md` | https://rydesharing.com/privacy-policy/ | Privacy Policy — data collection, use, disclosure, retention, user rights, in-vehicle recording |
| 9 | `ratings_moderation_policy.md` | Ryde Help Center | Ratings and Reviews Moderation Policy — review removal criteria, conflict of interest, relevance moderation |
| 10 | `dispute_appeals_policy.md` | Ryde Help Center | Dispute Appeals Policy — how to file appeals, cancellation fee appeals, ERP claims, cleaning claims, account suspension appeals, SIAC arbitration |
| 11 | `dispute_resolution_guide.md` | Synthesized from all official sources | **Dispute Resolution Guide** — maps all 7 hackathon dispute scenarios to official policy clauses with resolution steps, evidence requirements, and fault determination |

## Key Facts About Ryde

- **Company:** Ryde Technologies Pte. Ltd. (Singapore)
- **Business Model:** 0% commission for drivers (drivers take home 100% of earnings)
- **Services:** RydePOOL, RydeX, RydeXL, RydeTAXI, RydeFLASH, RydeHIRE, RydeLUXE, RydePET, Ryde+, RydeSEND
- **Governing Law:** Singapore law
- **Dispute Resolution:** Singapore International Arbitration Centre (SIAC); Partners may also use Singapore Mediation Centre or Small Claims Tribunal
- **Cleaning Fee:** Up to S$200 for professional cleaning (vomit, stains, spillage, soil)
- **Account Restoration Fee:** S$10.00 (excluding GST), waived if appeal approved
- **Cancellation Grace Period:** 3 minutes from driver arrival
- **Dormant Account:** 6 months (riders), 1 year (drivers)
- **RydeCoins:** Valid 6 months from last transaction, non-refundable, non-transferable
- **RydePOOL Limit:** Max 2 paid carpool trips per day (Singapore regulation)
- **RydeSEND Limit:** Max 40cm x 30cm x 30cm, 8 kg per delivery trip

## Dispute Scenario Coverage

All 7 hackathon dispute scenarios are covered:

| Scenario | Primary Documents | Key Policy Clauses |
|----------|-------------------|-------------------|
| 1. Route Deviation | `dispute_resolution_guide.md`, `terms_of_use.md`, `driver_guidelines.md` | Driver must travel directly to pickup; GPS telemetry determines fault; refund at Ryde's discretion |
| 2. No-Show Charge | `cancellation_policy.md`, `dispute_resolution_guide.md` | 3-min grace period; driver must arrive at correct location; timestamp/GPS evidence |
| 3. Fare Dispute | `dispute_resolution_guide.md`, `terms_of_use.md` | Fare breakdown verification; surge pricing display check; Ryde retains absolute discretion |
| 4. Cancellation Refund | `cancellation_policy.md`, `refund_policy.md` | Free cancellation before driver assignment; fee after assignment unless driver delayed >10 min |
| 5. Service Quality | `safety_standards.md`, `ratings_moderation_policy.md`, `dispute_resolution_guide.md` | P0-P3 incident classification; rating system; review moderation; formal warnings |
| 6. Property Damage | `refund_policy.md`, `driver_guidelines.md`, `dispute_resolution_guide.md` | Up to S$200 cleaning fee; photo evidence + receipt required; rider can dispute pre-existing damage |
| 7. Safety Incident | `safety_standards.md`, `rider_code_of_conduct.md`, `dispute_resolution_guide.md` | P0 = immediate suspension + police report; P1 = 24h review + warning; emergency: call 999 |

## Re-indexing

After updating policy documents, re-index into ChromaDB:

```bash
python scripts/index_policies.py --clear
```

Current index: **12 documents, 41 chunks** in ChromaDB (local persistent mode).
