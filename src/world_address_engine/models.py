"""Stable, side-effect-free contracts shared by file readers and classifiers."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

STATUSES = frozenset({
    "MATCHED", "REVIEW_AMBIGUOUS", "REVIEW_CONFLICT",
    "REVIEW_CODE_MAPPING", "UNKNOWN", "INPUT_ERROR",
})


@dataclass(frozen=True, slots=True)
class AddressRecord:
    record_no: int
    source_file: str
    source_sheet: str | None
    record_id: str | None
    fields: Mapping[str, str]
    address_text: str
    country_hint: str | None
    input_error: str | None = None

    def __post_init__(self) -> None:
        if self.record_no < 1:
            raise ValueError("record_no must be positive")
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True, slots=True)
class DestinationCandidate:
    destination_id: str
    evidence: tuple[str, ...]
    score: float

    def __post_init__(self) -> None:
        if not self.destination_id or not 0 <= self.score <= 1:
            raise ValueError("candidate requires destination_id and score between 0 and 1")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    record_no: int
    status: str
    hkp_code: str | None
    confidence: float
    reason: str
    destination_id: str | None

    def __post_init__(self) -> None:
        if self.record_no < 1 or self.status not in STATUSES or not 0 <= self.confidence <= 1:
            raise ValueError("invalid classification record, status or confidence")
        if self.status != "MATCHED" and self.hkp_code is not None:
            raise ValueError("non-MATCHED classification cannot assert HKP code")
        if self.status == "MATCHED" and (not self.hkp_code or not self.destination_id):
            raise ValueError("MATCHED classification requires a code and destination_id")
