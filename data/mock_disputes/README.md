# Synthetic Mock Disputes

This folder contains fictional dispute cases created for the Tencent Cloud
Hackathon demonstration.

All names, trips, GPS records, payment amounts, policies, and outcomes are
synthetic. They do not represent official Ryde records or policies.

## Format

Every file follows the DISP-002 sample dataset format
(`data/Dispute_format/`): `dispute_ticket`, `rider_profile`, `driver_profile`,
`trip_data`, `gps_telemetry`, `chat_logs`, `app_events`, plus the policy that
applied to the trip (`cancellation_policy` for no-show / cancellation cases,
`platform_policy` for the others).

`trip_data` holds the fields that matter for the dispute type: wait and
cancellation times for no-show / cancellation cases, distance, duration and
fare for completed trips.

`expected_outcome` is the answer key for evaluation. The API client strips it
before any agent sees the data. `verdict: null` with
`requires_human_review: true` means the correct result is escalation, not a
ruling.

## Cases

| File | Trip | Type | Expected |
|---|---|---|---|
| route_deviation_01 | RYDE-DEMO-001 | route_deviation | upheld, refund S$3.70 (driver missed exit) |
| route_deviation_02 | RYDE-DEMO-002 | route_deviation | dismissed (road closure, rider agreed to detour) |
| no_show_01 | RYDE-DEMO-003 | no_show | upheld, refund S$8.00 (driver never arrived) |
| no_show_02 | RYDE-DEMO-004 | no_show | dismissed (driver waited 8 min, rider late) |
| fare_dispute_01 | RYDE-DEMO-005 | fare_dispute | upheld, refund S$8.20 (surge applied after confirmation) |
| fare_dispute_02 | RYDE-DEMO-006 | fare_dispute | dismissed (rider accepted displayed surge) |
| cancellation_refund_01 | RYDE-DEMO-007 | cancellation_refund | upheld, refund S$4.00 (driver >10 min late) |
| cancellation_refund_02 | RYDE-DEMO-008 | cancellation_refund | dismissed (rider cancelled, driver on time) |
| service_quality_01 | RYDE-DEMO-009 | service_quality | partially upheld, P1 formal warning |
| safety_incident_01 | RYDE-DEMO-010 | service_quality (P0 in text) | escalate to human, P0 |
| driver_rights_01 | RYDE-DEMO-011 | driver_rights (filed by driver) | upheld, charge rider S$120 cleaning |
| cleaning_fee_01 | RYDE-DEMO-012 | cleaning_fee (unmapped, classifier decides) | upheld, refund S$150 (pre-existing stain) |
| no_show_03 | RYDE-DEMO-013 | no_show, no GPS | escalate to human (insufficient evidence) |
