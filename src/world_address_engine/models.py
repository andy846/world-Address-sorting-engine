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
    # `support` is the raw, explainable evidence mass for this destination.
    # `score` is the same value capped for reporting. Counting matched rows
    # instead saturates on a global gazetteer, where one city name matches
    # places in a dozen countries, so the aggregate is kept separately.
    support: float = 0.0
    token_count: int = 0
    country_entity: bool = False
    entity_terms: tuple[str, ...] = ()
    # The GeoNames feature code behind each entity term. This distinguishes a
    # sovereign country (PCLI) from a semi-independent territory (PCLS).
    entity_feature_codes: tuple[tuple[str, str], ...] = ()
    # Per-term evidence mass: (search term, weight) pairs, heaviest first.
    # The classifier needs the breakdown to withdraw evidence that turns out
    # to belong to a company name rather than to a destination.
    term_support: tuple[tuple[str, float], ...] = ()
    # Complete bounded contributions, independent of truncated display evidence.
    place_support: tuple[tuple[str, float, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.destination_id or not 0 <= self.score <= 1:
            raise ValueError("candidate requires destination_id and score between 0 and 1")
        if self.support < 0:
            raise ValueError("candidate support cannot be negative")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    record_no: int
    status: str
    hkp_code: str | None
    confidence: float
    reason: str
    destination_id: str | None
    # The geographic terms that produced the decision, and the destination
    # names from the approved catalogue. Both are audit output.
    evidence: tuple[str, ...] = ()
    destination_name_en: str = ""
    destination_name_tc: str = ""

    def __post_init__(self) -> None:
        if self.record_no < 1 or self.status not in STATUSES or not 0 <= self.confidence <= 1:
            raise ValueError("invalid classification record, status or confidence")
        if self.status != "MATCHED" and self.hkp_code is not None:
            raise ValueError("non-MATCHED classification cannot assert HKP code")
        if self.status == "MATCHED" and (not self.hkp_code or not self.destination_id):
            raise ValueError("MATCHED classification requires a code and destination_id")
        object.__setattr__(self, "evidence", tuple(self.evidence))
