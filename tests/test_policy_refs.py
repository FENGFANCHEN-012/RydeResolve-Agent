"""Citation normalisation: real case-policy keys written loosely must survive the whitelist."""
from src.core.policy_refs import normalize_case_policy_ref

VALID = {
    "platform_policy.free_cancellation_within_min_of_match",
    "platform_policy.cancellation_fee_after_driver_assigned",
    "Ryde Help Rider Booking A Ryde#3",
}


def test_exact_ref_unchanged():
    assert normalize_case_policy_ref("Ryde Help Rider Booking A Ryde#3", VALID) == "Ryde Help Rider Booking A Ryde#3"


def test_bare_key_gets_section():
    assert normalize_case_policy_ref("free_cancellation_within_min_of_match", VALID) == \
        "platform_policy.free_cancellation_within_min_of_match"


def test_other_section_name_is_mapped():
    assert normalize_case_policy_ref("cancellation_policy.cancellation_fee_after_driver_assigned", VALID) == \
        "platform_policy.cancellation_fee_after_driver_assigned"


def test_key_with_value_suffix_is_kept():
    # Seen in eval run 20260930-132225 (CR-002-P3): the Judge cited "key = value"
    assert normalize_case_policy_ref("free_cancellation_within_min_of_match = 3", VALID) == \
        "platform_policy.free_cancellation_within_min_of_match"
    assert normalize_case_policy_ref("platform_policy.cancellation_fee_after_driver_assigned = 4.0", VALID) == \
        "platform_policy.cancellation_fee_after_driver_assigned"


def test_unknown_key_is_left_for_the_whitelist():
    assert normalize_case_policy_ref("made_up_rule = 5", VALID) == "made_up_rule = 5"


def test_key_with_colon_note_is_kept():
    # Seen in eval run 20260930-132225 (RD-002): "key: value (explanation)"
    valid = VALID | {"platform_policy.fare_basis"}
    assert normalize_case_policy_ref("fare_basis: metered (RydeTAXI fares are not fixed upfront)", valid) ==         "platform_policy.fare_basis"


def test_free_text_with_colon_is_not_rescued():
    assert normalize_case_policy_ref("Refund policy: riders always get money back", VALID) ==         "Refund policy: riders always get money back"
