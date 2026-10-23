import pytest
from world_address_engine.models import AddressRecord, ClassificationResult, DestinationCandidate, STATUSES


def test_nonmatched_result_never_contains_asserted_hkp_code():
    with pytest.raises(ValueError, match="cannot assert"):
        ClassificationResult(1, "UNKNOWN", "US", 0.0, "no evidence", None)


def test_matched_result_requires_a_destination_code():
    with pytest.raises(ValueError, match="requires"):
        ClassificationResult(1, "MATCHED", None, 1.0, "country", "us")


def test_address_record_keeps_original_fields():
    fields = {"Address": "台北市", "Reference": "00001"}
    record = AddressRecord(1, "jobs.csv", None, "00001", fields, fields["Address"], None)
    fields["Address"] = "tampered"
    assert record.fields["Address"] == "台北市"
    with pytest.raises(TypeError):
        record.fields["Address"] = "mutated"


def test_scores_outside_zero_one_are_rejected():
    with pytest.raises(ValueError):
        DestinationCandidate("jp", ("Tokyo",), 1.01)


def test_status_enumeration_is_fixed():
    assert set(STATUSES) == {"MATCHED", "REVIEW_AMBIGUOUS", "REVIEW_CONFLICT", "REVIEW_CODE_MAPPING", "UNKNOWN", "INPUT_ERROR"}
