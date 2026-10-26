import csv
import hashlib
import importlib
import json
from types import SimpleNamespace

import pytest

from world_address_engine.models import AddressRecord


def catalogue():
    return SimpleNamespace(entries={
        'IN': SimpleNamespace(code='IN', name_en='India', name_tc='India TC', aliases=()),
        'JP': SimpleNamespace(code='JP', name_en='Japan', name_tc='Japan TC', aliases=()),
    })


def pair(number, code, status, fields=None):
    record = AddressRecord(number, 'synthetic.csv', None, '0001',
                           fields or {'ID': '0001', 'Address': '=synthetic'},
                           'synthetic', None)
    result = SimpleNamespace(record_no=number, country_code=code, status=status,
                             reason='SYNTHETIC_REASON', candidates=(),
                             evidence=('PRIVATE_EVIDENCE_MUST_NOT_EXPORT',))
    return record, result


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def test_reports_conserve_counts_and_publish_safe_minimal_files(tmp_path):
    reports = importlib.import_module('world_address_engine.io.country_reports')
    result = reports.write_country_reports(iter([
        pair(1, 'IN', 'DETERMINED'), pair(2, 'JP', 'INFERRED'),
        pair(3, None, 'UNRESOLVED'), pair(4, 'IN', 'DETERMINED'),
    ]), tmp_path, catalogue(), {'rules_version': 'synthetic-rules'})
    assert result['status_counts'] == {'DETERMINED': 2, 'INFERRED': 1, 'UNRESOLVED': 1}
    assert result['destination_counts'] == {'IN': 2, 'JP': 1}
    assert result['total_records'] == 4
    rows = read(tmp_path / 'Classified_Addresses.csv')
    assert list(rows[0]) == ['ID', 'Address', 'Country_Code', 'Zone_Code', 'NOVSN_Zone_Code']
    assert rows[0] == {'ID': '0001', 'Address': "'=synthetic", 'Country_Code': 'IN',
                       'Zone_Code': '1', 'NOVSN_Zone_Code': 'C'}
    assert [row['Country_Code'] for row in rows] == ['IN', 'JP', '', 'IN']
    assert read(tmp_path / 'Country_Summary.csv') == [
        {'Country_Code': 'IN', 'Country_Name_TC': 'India TC', 'Country_Name_EN': 'India',
         'Zone_Code': '1', 'NOVSN_Zone_Code': 'C', 'Count': '2', 'Percentage': '50.00'},
        {'Country_Code': 'JP', 'Country_Name_TC': 'Japan TC', 'Country_Name_EN': 'Japan',
         'Zone_Code': '2', 'NOVSN_Zone_Code': 'D', 'Count': '1', 'Percentage': '25.00'},
        {'Country_Code': '', 'Country_Name_TC': '', 'Country_Name_EN': '',
         'Zone_Code': '', 'NOVSN_Zone_Code': '', 'Count': '1', 'Percentage': '25.00'},
    ]
    diagnostics = (tmp_path / 'Country_Diagnostics.csv').read_text(encoding='utf-8-sig')
    assert 'PRIVATE_EVIDENCE' not in diagnostics and '=synthetic' not in diagnostics
    assert list(read(tmp_path / 'Country_Diagnostics.csv')[0]) == [
        'Source_Record_No', 'Status', 'Reason', 'Candidates']
    manifest = json.loads((tmp_path / 'Run_Manifest.json').read_text(encoding='utf8'))
    assert manifest == result
    assert manifest['job_kind'] == 'country-analysis'
    assert manifest['data_class'] == 'COUNTRY_CODE_ESTIMATE'
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize('code,status', [('ZZ', 'INFERRED'), ('IN', 'UNRESOLVED'),
                                        (None, 'DETERMINED'), ('IN', 'BAD')])
def test_invalid_inference_never_publishes(tmp_path, code, status):
    reports = importlib.import_module('world_address_engine.io.country_reports')
    with pytest.raises(ValueError):
        reports.write_country_reports(iter([pair(1, code, status)]), tmp_path,
                                      catalogue(), {})
    assert not (tmp_path / 'Run_Manifest.json').exists()
    assert list(tmp_path.iterdir()) == []


def test_manifest_is_last_and_completed_outputs_are_immutable(tmp_path):
    reports = importlib.import_module('world_address_engine.io.country_reports')

    def before_manifest():
        assert not (tmp_path / 'Run_Manifest.json').exists()
        assert (tmp_path / 'Country_Diagnostics.csv').is_file()
        assert not list(tmp_path.glob('.country-report-*'))

    reports.write_country_reports(iter([pair(1, 'IN', 'DETERMINED')]), tmp_path,
                                  catalogue(), {}, before_manifest=before_manifest)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(FileExistsError):
        reports.write_country_reports(iter([]), tmp_path, catalogue(), {})
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_empty_report_preserves_original_columns(tmp_path):
    reports = importlib.import_module('world_address_engine.io.country_reports')
    report = reports.write_country_reports(iter([]), tmp_path, catalogue(), {},
                                           original_columns=['ID', 'Address', 'Unnamed_1'])
    assert report['total_records'] == 0
    with (tmp_path / 'Classified_Addresses.csv').open(encoding='utf-8-sig') as stream:
        assert next(csv.reader(stream)) == ['ID', 'Address', 'Unnamed_1', 'Country_Code',
                                          'Zone_Code', 'NOVSN_Zone_Code']


def test_formula_headers_are_neutralized_and_existing_country_column_is_preserved(tmp_path):
    reports = importlib.import_module('world_address_engine.io.country_reports')
    reports.write_country_reports(iter([pair(1, 'JP', 'DETERMINED',
        {'=Header': '0007', 'Country_Code': 'original-code'})]), tmp_path, catalogue(), {})
    with (tmp_path / 'Classified_Addresses.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert list(csv.reader(stream)) == [
            ["'=Header", 'Country_Code', 'Country_Code', 'Zone_Code', 'NOVSN_Zone_Code'],
            ['0007', 'original-code', 'JP', '2', 'D']]
