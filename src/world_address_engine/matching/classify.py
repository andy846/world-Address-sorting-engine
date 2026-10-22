"""Conservative address-to-Hongkong-Post code decision engine (offline).

Only reviewed HKP_DESTINATION_2 codes may be output, never ISO fallbacks.
The confidence value is a heuristic, NOT calibrated postal accuracy.
"""
import sqlite3
from pathlib import Path
from world_address_engine.models import AddressRecord, ClassificationResult
from world_address_engine.matching.normalize import contains_name, normalize_address, has_unsupported_script
from world_address_engine.matching.retrieve import retrieve_candidates


def _postal_catalogue(path: Path):
    with sqlite3.connect(path) as db:
        rows=db.execute('''SELECT destination_id,code,name_en,name_zh_hant,name_zh_hans
                           FROM destinations WHERE code_scheme='HKP_DESTINATION_2'
                           AND profile='HKP_DESTINATION_2' AND approval_status='APPROVED' ''').fetchall()
        iso=dict(db.execute('''SELECT code,destination_id FROM destinations
                              WHERE code_scheme='ISO_ALPHA2' AND profile='ISO'
                              AND approval_status='APPROVED' ''').fetchall())
    codes={r[0]:r[1] for r in rows}
    names={r[0]:(r[2],r[3],r[4]) for r in rows}
    return codes,names,iso


def classify_record(record: AddressRecord, geo_db: Path, hkp_db: Path) -> ClassificationResult:
    def result(status, code=None, confidence=0., reason='', destination_id=None):
        return ClassificationResult(record.record_no,status,code,confidence,reason,destination_id)
    if record.input_error:
        return result('INPUT_ERROR',reason=record.input_error)
    if not record.address_text.strip() and not record.country_hint:
        return result('UNKNOWN',reason='EMPTY_ADDRESS')
    if has_unsupported_script(record.address_text):
        return result('UNKNOWN',reason='UNSUPPORTED_LANGUAGE')
    codes,names,iso=_postal_catalogue(Path(hkp_db))
    # Avoid treating a company name such as "Hong Kong Holdings" on the
    # recipient-name line as destination evidence when other lines exist.
    lines=[s.strip() for s in record.address_text.splitlines() if s.strip()]
    country_scope='\n'.join(lines[1:]) if len(lines)>1 else record.address_text
    explicit=set()
    for did, aliases in names.items():
        for alias in aliases:
            if alias and contains_name(country_scope,alias):
                explicit.add(did)
                break
    if record.country_hint:
        hint=record.country_hint.strip()
        for did,code in codes.items():
            if hint.upper()==code or any(hint.casefold()==v.casefold() for v in names[did] if v):
                explicit.add(did)
        if hint.upper() in iso:
            explicit.add(iso[hint.upper()])
    if len(explicit)>1:
        return result('REVIEW_CONFLICT',reason='CONTRADICTORY_EXPLICIT_DESTINATIONS')
    candidates=retrieve_candidates(Path(geo_db),normalize_address(record.address_text),record.country_hint)
    if explicit:
        did=next(iter(explicit))
        # A destination with enough independently corroborated evidence
        # from ANOTHER country indicates an actual conflicting address.
        contradicting=[c for c in candidates if c.score>=.87 and iso.get(c.destination_id)!=did]
        if contradicting:
            return result('REVIEW_CONFLICT',reason='EXPLICIT_DESTINATION_CONFLICTS_WITH_GEOGRAPHY')
        return result('MATCHED',codes[did],.98,'EXPLICIT_DESTINATION',did)
    if not candidates:
        return result('UNKNOWN',reason='NO_GEOGRAPHIC_MATCH')
    best=candidates[0]
    if best.score < .87:
        if len(candidates)>1:
            return result('REVIEW_AMBIGUOUS',reason='MULTIPLE_PLAUSIBLE_GEOGRAPHIC_DESTINATIONS')
        return result('UNKNOWN',reason='SINGLE_PLACE_IS_NOT_ENOUGH')
    runners=[c for c in candidates[1:] if c.score >= .87]
    if runners:
        return result('REVIEW_AMBIGUOUS',reason='MULTIPLE_STRONG_GEOGRAPHIC_DESTINATIONS')
    did=iso.get(best.destination_id)
    if not did or did not in codes:
        return result('REVIEW_CODE_MAPPING',reason='GEOGRAPHY_HAS_NO_APPROVED_HKP_MAPPING')
    return result('MATCHED',codes[did],best.score,'MULTIPLE_LINKED_GEOGRAPHIC_PLACES',did)
