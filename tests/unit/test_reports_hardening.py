"""Export labelling, formula safety and the required detailed fields.

Covers audit findings 9 (test-only exports are indistinguishable from
production exports), 11 (the summary bypasses the formula sanitizer) and
12 (the detailed export omits required fields).
"""

import csv
import json

import pytest

from world_address_engine.io.reports import RESULT_FIELDS, write_reports
from world_address_engine.models import AddressRecord, ClassificationResult


def pair(n, status="MATCHED", code=None, destination_id=None, evidence=()):
    row = AddressRecord(n, 'test.csv', None, f'{n:05d}',
                        {'Address': 'x', 'Control no': f'{n:05d}'}, 'x', None)
    result = ClassificationResult(n, status, code, 0.9 if code else 0.0,
                                  'GEOGRAPHIC_EVIDENCE', destination_id,
                                  evidence=evidence)
    return row, result


def read(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


TEST_ONLY = {'data_approval': 'TEST_ONLY_UNVERIFIED'}
PRODUCTION = {'data_approval': 'INDEPENDENTLY_AUDITED'}


def test_test_only_export_is_visibly_marked_in_every_file(tmp_path):
    write_reports(iter([pair(1, code='JP', destination_id='japan')]), tmp_path, TEST_ONLY)
    for name in ('Classified_Addresses.csv', 'Country_Summary.csv'):
        rows = read(tmp_path / name)
        assert rows, name
        assert rows[0]['Data_Class'] == 'TEST_ONLY_UNVERIFIED', name
    marker = (tmp_path / 'DATA_CLASS.txt').read_text(encoding='utf-8')
    assert 'TEST_ONLY_UNVERIFIED' in marker
    manifest = json.loads((tmp_path / 'Run_Manifest.json').read_text(encoding='utf-8'))
    assert manifest['data_class'] == 'TEST_ONLY_UNVERIFIED'


def test_production_export_is_visibly_marked(tmp_path):
    write_reports(iter([pair(1, code='JP', destination_id='japan')]), tmp_path, PRODUCTION)
    rows = read(tmp_path / 'Classified_Addresses.csv')
    assert rows[0]['Data_Class'] == 'PRODUCTION_APPROVED'
    assert 'PRODUCTION_APPROVED' in (tmp_path / 'DATA_CLASS.txt').read_text(encoding='utf-8')


def test_country_summary_is_formula_safe(tmp_path):
    write_reports(iter([pair(1, code='=2+2', destination_id='x')]), tmp_path, PRODUCTION)
    rows = read(tmp_path / 'Country_Summary.csv')
    assert rows[0]['HKP_Destination_Code'] == "'=2+2"


def test_detailed_export_carries_every_required_field(tmp_path):
    required = ('Destination_Name_EN', 'Destination_Name_TC', 'Match_Method',
                'Match_Evidence', 'Review_Reason', 'HKP_Catalogue_Version',
                'Geo_Pack_Versions', 'Rules_Version', 'Data_Class')
    for field in required:
        assert field in RESULT_FIELDS, field
    write_reports(iter([pair(1, code='JP', destination_id='japan',
                             evidence=('japan',))]),
                  tmp_path, {**PRODUCTION, 'catalogue_version': '2026.10',
                             'geo_pack_versions': 'geonames-2026-10-22',
                             'rules_version': '2026-10-23.2'})
    row = read(tmp_path / 'Classified_Addresses.csv')[0]
    assert row['HKP_Catalogue_Version'] == '2026.10'
    assert row['Geo_Pack_Versions'] == 'geonames-2026-10-22'
    assert row['Rules_Version'] == '2026-10-23.2'
    assert row['Match_Method'] == 'GEOGRAPHIC_EVIDENCE'
    assert row['Match_Evidence'] == 'japan'
    assert row['Review_Reason'] == ''


def test_review_rows_carry_their_review_reason(tmp_path):
    write_reports(iter([pair(1, status='REVIEW_AMBIGUOUS')]), tmp_path, PRODUCTION)
    row = read(tmp_path / 'Manual_Review.csv')[0]
    assert row['Classification_Status'] == 'REVIEW_AMBIGUOUS'
    assert row['Review_Reason'] == 'GEOGRAPHIC_EVIDENCE'
    assert row['HKP_Destination_Code'] == ''


def test_an_unapproved_code_fails_the_export(tmp_path):
    from world_address_engine.io.reports import CodeApprovalError
    try:
        write_reports(iter([pair(1, code='ZZ', destination_id='atlantis')]), tmp_path,
                      PRODUCTION, code_validator=lambda destination_id, code: code == 'JP')
    except CodeApprovalError:
        pass
    else:
        raise AssertionError('expected the export to refuse an unapproved code')
    assert not (tmp_path / 'Run_Manifest.json').exists()


def test_export_fails_closed_when_the_code_validator_is_missing(tmp_path):
    """Without an approval the exporter refuses to publish a code."""
    from world_address_engine.io.reports import CodeApprovalError
    try:
        write_reports(iter([pair(1, code='JP', destination_id='japan')]), tmp_path,
                      PRODUCTION, code_validator=None, require_validated_codes=True)
    except CodeApprovalError:
        pass
    else:
        raise AssertionError('expected the export to refuse to publish a code')
    assert not (tmp_path / 'Run_Manifest.json').exists()


def test_staging_cleanup_failure_never_publishes_a_complete_manifest(
        tmp_path, monkeypatch):
    """Plaintext staging data may not be silently retained behind COMPLETE."""
    from world_address_engine.io import reports

    def leave_staging_in_place(*args, **kwargs):
        return None

    monkeypatch.setattr(reports.shutil, 'rmtree', leave_staging_in_place)
    with pytest.raises(OSError, match='staging|cleanup'):
        write_reports(
            iter([pair(1, code='JP', destination_id='japan')]),
            tmp_path,
            PRODUCTION,
        )
    assert not (tmp_path / 'Run_Manifest.json').exists()
    assert not list(tmp_path.glob('.pending-manifest-*'))
