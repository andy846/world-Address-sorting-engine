"""Audited manual quality-control decisions.

Every operator decision is appended to a local JSONL ledger with the
operator, the time, the original and the new result, the reason, and the
pack and catalogue versions in force. A decision applies to exactly one
input record; rows that happen to share the same address are untouched.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REVIEW_CSV_NAME = 'Review_Corrections.csv'

REVIEW_FIELDS = (
    'Source_Record_No', 'Record_ID', 'Operator', 'Decided_At',
    'Original_Status', 'Original_Code', 'Original_Reason',
    'New_Status', 'New_Code', 'Reason',
    'HKP_Catalogue_Version', 'Geo_Pack_Versions', 'Rules_Version',
    'Approval_ID', 'Approval_Manifest_SHA256',
)


class ReviewError(ValueError):
    """Raised when a review decision is not acceptable."""


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    record_no: int
    record_id: str
    operator: str
    decided_at: str
    original_status: str
    original_code: str | None
    original_reason: str
    new_status: str
    new_code: str | None
    reason: str
    catalogue_version: str
    geo_pack_versions: str
    rules_version: str = ''
    approval_id: str = ''
    approval_manifest_sha256: str = ''


class ReviewStore:
    """An append-only ledger of manual corrections for one job."""

    def __init__(self, path: Path, *, operator: str, catalogue_version: str = '',
                 geo_pack_versions: str = '', rules_version: str = '',
                 approval_id: str = '', approval_manifest_sha256: str = ''):
        self.path = Path(path)
        self.operator = operator
        self.catalogue_version = catalogue_version
        self.geo_pack_versions = geo_pack_versions
        self.rules_version = rules_version
        self.approval_id = approval_id
        self.approval_manifest_sha256 = approval_manifest_sha256
        self._decisions: list[ReviewDecision] = []
        if self.path.is_file():
            self._load()

    def _load(self) -> None:
        with self.path.open(encoding='utf-8') as stream:
            for line in stream:
                line = line.strip()
                if line:
                    payload = json.loads(line)
                    # Ledgers written by an earlier build lack the newer
                    # provenance columns; they stay readable.
                    for field in ('rules_version', 'approval_id',
                                  'approval_manifest_sha256'):
                        payload.setdefault(field, '')
                    self._decisions.append(ReviewDecision(**payload))

    def decisions(self) -> tuple[ReviewDecision, ...]:
        return tuple(self._decisions)

    def latest_by_record(self) -> dict[int, ReviewDecision]:
        """The most recent decision for each record."""
        latest: dict[int, ReviewDecision] = {}
        for decision in self._decisions:
            latest[decision.record_no] = decision
        return latest

    def decide(self, record_no: int, *, record_id: str = '', original_status: str = '',
               original_code: str | None = None, original_reason: str = '',
               new_code: str | None = None, reason: str = '',
               approved_codes: dict[str, str] | None = None) -> ReviewDecision:
        """Record one correction. Only an approved code may be asserted."""
        if record_no < 1:
            raise ReviewError('a decision needs a positive source record number')
        if not self.operator.strip():
            raise ReviewError('an operator name is required')
        if not reason.strip():
            raise ReviewError('a reason is required for every manual decision')
        if new_code is not None:
            if not approved_codes:
                raise ReviewError('no approved catalogue is available for review')
            if new_code not in set(approved_codes.values()):
                raise ReviewError('the chosen code is not an approved destination code')
        decision = ReviewDecision(
            record_no=record_no,
            record_id=record_id,
            operator=self.operator.strip(),
            decided_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            original_status=original_status,
            original_code=original_code,
            original_reason=original_reason,
            new_status='MATCHED' if new_code else original_status,
            new_code=new_code,
            reason=reason.strip(),
            catalogue_version=self.catalogue_version,
            geo_pack_versions=self.geo_pack_versions,
            rules_version=self.rules_version,
            approval_id=self.approval_id,
            approval_manifest_sha256=self.approval_manifest_sha256,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(asdict(decision), ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        self._decisions.append(decision)
        return decision

    def write_csv(self, path: Path | None = None) -> Path:
        """Write the operator-facing correction log."""
        target = Path(path) if path else self.path.with_name(REVIEW_CSV_NAME)
        with target.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(REVIEW_FIELDS))
            writer.writeheader()
            for decision in self._decisions:
                writer.writerow({
                    'Source_Record_No': decision.record_no,
                    'Record_ID': decision.record_id,
                    'Operator': decision.operator,
                    'Decided_At': decision.decided_at,
                    'Original_Status': decision.original_status,
                    'Original_Code': decision.original_code or '',
                    'Original_Reason': decision.original_reason,
                    'New_Status': decision.new_status,
                    'New_Code': decision.new_code or '',
                    'Reason': decision.reason,
                    'HKP_Catalogue_Version': decision.catalogue_version,
                    'Geo_Pack_Versions': decision.geo_pack_versions,
                    'Rules_Version': decision.rules_version,
                    'Approval_ID': decision.approval_id,
                    'Approval_Manifest_SHA256': decision.approval_manifest_sha256,
                })
        return target
