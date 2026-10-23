"""The manual QC path must never be weaker than the engine that produced the
export.

The independent review of commit 0957f1d found that ``apply_review_corrections``
wrote a destination code straight from a local JSONL ledger, without checking
it against the approved catalogue, and that it left ``Manual_Review.csv``
stale. Every case here is a RED test for one of those findings.
"""

import csv
import json
from pathlib import Path

import pytest

from world_address_engine.io.reports import (
    CodeApprovalError,
    apply_review_corrections,
)
from world_address_engine.gui.review_store import ReviewStore
from world_address_engine.jobs.runner import run_job
from tests.unit.test_classify import hkp
from tests.unit.test_retrieve import geo


def source(path: Path, addresses):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2'])
        for address in addresses:
            writer.writerow(['Recipient', address])


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def run(tmp_path, addresses, **kwargs):
    data = tmp_path / 'sample.csv'
    source(data, addresses)
    master = hkp(tmp_path)
    out = tmp_path / 'out'
    run_job(data, out, geo(tmp_path), master.db_path, {},
            batch_size=10, allow_unverified_reference_data=True,
            approval_manifest=master.manifest_path,
            approval_key=master.key_path, **kwargs)
    return out, master


def approved_lookup(master):
    """Resolve an approved code to the destination the approval ratified."""
    from world_address_engine.hkp.catalogue import approved_codes
    codes = approved_codes(master.db_path, master.approval)
    names = {}
    from world_address_engine.sqlite_util import open_db
    with open_db(master.db_path) as conn:
        for row in conn.execute(
                "SELECT destination_id, name_en, name_zh_hant FROM destinations "
                "WHERE code_scheme='HKP_DESTINATION_2'"):
            names[row[0]] = (row[1], row[2])

    def lookup(code):
        for destination_id, approved in codes.items():
            if approved != code:
                continue
            name_en, name_tc = names.get(destination_id, ('', ''))
            return {'destination_id': destination_id, 'name_en': name_en,
                    'name_tc': name_tc}
        return None

    return lookup


def decision(store, record_no, new_code, reason='operator confirmed'):
    return store.decide(record_no, new_code=new_code, reason=reason,
                        approved_codes={'united-states': 'US', 'india': 'IN'})


def test_a_code_outside_the_approved_catalogue_is_refused(tmp_path):
    """A hand-edited ledger must not be able to inject a destination code."""
    out, master = run(tmp_path, ['Springfield', 'Mumbai, India'])
    ledger = out / 'review_decisions.jsonl'
    ledger.write_text(json.dumps({
        'record_no': 1, 'record_id': '', 'operator': 'attacker',
        'decided_at': '2026-10-23T00:00:00+00:00',
        'original_status': 'REVIEW_AMBIGUOUS', 'original_code': None,
        'original_reason': 'SINGLE_PLACE_IS_NOT_ENOUGH', 'new_status': 'MATCHED',
        'new_code': 'ZZ', 'reason': 'trust me', 'catalogue_version': '',
        'geo_pack_versions': '',
    }) + '\n', encoding='utf-8')
    store = ReviewStore(ledger, operator='attacker')
    with pytest.raises(CodeApprovalError):
        apply_review_corrections(out, store.decisions(),
                                 approved_destination=approved_lookup(master),
                                 require_validated_codes=True)
    rows = read(out / 'Classified_Addresses.csv')
    assert rows[0]['HKP_Destination_Code'] == ''


def test_a_correction_updates_the_manual_review_file(tmp_path):
    out, master = run(tmp_path, ['Springfield', 'Springfield', 'Mumbai, India'])
    store = ReviewStore(out / 'review.jsonl', operator='Ada')
    decision(store, 1, 'US')
    apply_review_corrections(out, store.decisions(),
                             approved_destination=approved_lookup(master),
                             require_validated_codes=True)
    manual = read(out / 'Manual_Review.csv')
    assert [row['Source_Record_No'] for row in manual] == ['2']
    details = read(out / 'Classified_Addresses.csv')
    assert details[0]['HKP_Destination_Code'] == 'US'
    assert len(details) == 3


def test_a_corrected_row_keeps_its_destination_identity(tmp_path):
    out, master = run(tmp_path, ['Springfield', 'Mumbai, India'])
    store = ReviewStore(out / 'review.jsonl', operator='Ada')
    decision(store, 1, 'US')
    apply_review_corrections(out, store.decisions(),
                             approved_destination=approved_lookup(master),
                             require_validated_codes=True)
    row = read(out / 'Classified_Addresses.csv')[0]
    assert row['Destination_ID'] == 'us'
    assert row['Destination_Name_EN'] == 'United States'
    assert row['Confidence_Score'] == '1.0'


def test_the_counts_still_reconcile_after_a_correction(tmp_path):
    out, master = run(tmp_path, ['Springfield', 'Mumbai, India'])
    store = ReviewStore(out / 'review.jsonl', operator='Ada')
    decision(store, 1, 'US')
    apply_review_corrections(out, store.decisions(),
                             approved_destination=approved_lookup(master),
                             require_validated_codes=True)
    manifest = json.loads((out / 'Run_Manifest.json').read_text(encoding='utf8'))
    assert manifest['total_records'] == 2
    assert sum(manifest['status_counts'].values()) == 2
    assert manifest['status_counts']['MATCHED'] == 2
    assert sum(manifest['destination_counts'].values()) == 2


def test_the_audit_artefacts_are_covered_by_the_manifest(tmp_path):
    out, master = run(tmp_path, ['Springfield', 'Mumbai, India'])
    store = ReviewStore(out / 'review.jsonl', operator='Ada')
    decision(store, 1, 'US')
    store.write_csv(out / 'Review_Corrections.csv')
    apply_review_corrections(out, store.decisions(),
                             approved_destination=approved_lookup(master),
                             require_validated_codes=True)
    manifest = json.loads((out / 'Run_Manifest.json').read_text(encoding='utf8'))
    digests = manifest['sha256']
    assert 'Review_Corrections.csv' in digests
    assert 'Manual_Review.csv' in digests


def test_a_tampered_summary_cannot_relabel_the_export(tmp_path):
    out, master = run(tmp_path, ['Springfield', 'Mumbai, India'])
    summary = out / 'Country_Summary.csv'
    summary.write_text('HKP_Destination_Code,Count,Data_Class\r\nUS,9,PRODUCTION_APPROVED\r\n',
                       encoding='utf-8-sig')
    store = ReviewStore(out / 'review.jsonl', operator='Ada')
    decision(store, 1, 'US')
    apply_review_corrections(out, store.decisions(),
                             approved_destination=approved_lookup(master),
                             require_validated_codes=True)
    rows = read(summary)
    assert rows[0]['Data_Class'] == 'TEST_ONLY_UNVERIFIED'


def test_the_operator_reason_is_spreadsheet_safe(tmp_path):
    out, master = run(tmp_path, ['Springfield', 'Mumbai, India'])
    store = ReviewStore(out / 'review.jsonl', operator='Ada')
    decision(store, 1, 'US', reason='=HYPERLINK("http://evil.example","x")')
    apply_review_corrections(out, store.decisions(),
                             approved_destination=approved_lookup(master),
                             require_validated_codes=True)
    row = read(out / 'Classified_Addresses.csv')[0]
    assert not row['Match_Evidence'].startswith('=')
    assert row['Match_Evidence'].startswith("'=")
