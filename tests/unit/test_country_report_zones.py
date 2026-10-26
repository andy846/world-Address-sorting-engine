"""Zone fields are derived business mappings, never extra country evidence."""
import csv
import json
from types import SimpleNamespace

import pytest

from tests.unit.test_country_reports import pair, read
from world_address_engine.io.country_reports import write_country_reports


def catalogue():
    return SimpleNamespace(entries={code: SimpleNamespace(code=code,name_en=code,name_tc=code,aliases=())
                                    for code in ('CN','HK','JP','MO','TW','TP','XO','XK')})


def test_detail_and_summary_append_literal_zone_mappings(tmp_path):
    report = write_country_reports(iter([pair(1,'CN','DETERMINED'),pair(2,'HK','INFERRED'),
        pair(3,'JP','DETERMINED'),pair(4,None,'UNRESOLVED')]),tmp_path,catalogue(),{})
    rows = read(tmp_path / 'Classified_Addresses.csv')
    assert list(rows[0])[-3:] == ['Country_Code','Zone_Code','NOVSN_Zone_Code']
    assert [(r['Country_Code'],r['Zone_Code'],r['NOVSN_Zone_Code']) for r in rows] == [
        ('CN','CN - Airmail','F'),('HK','LOCAL','A'),('JP','2','D'),('','','')]
    summaries = {r['Country_Code']:r for r in read(tmp_path/'Country_Summary.csv')}
    assert summaries['CN']['Zone_Code'] == 'CN - Airmail'
    assert summaries['HK']['NOVSN_Zone_Code'] == 'A'
    assert report['report_schema_version'] == 2
    assert report['generated_columns'] == ['Country_Code','Zone_Code','NOVSN_Zone_Code']
    assert set(report['run_metadata']['zone_mapping']) == {'version','source_sha256','sha256'}
    assert list(read(tmp_path/'Country_Diagnostics.csv')[0]) == ['Source_Record_No','Status','Reason','Candidates']


def test_original_generated_name_columns_are_preserved_positionally(tmp_path):
    original = {'Country_Code':'original','Zone_Code':'keep-zone','NOVSN_Zone_Code':'keep-novsn'}
    write_country_reports(iter([pair(1,'HK','INFERRED',original)]),tmp_path,catalogue(),{})
    with (tmp_path/'Classified_Addresses.csv').open(encoding='utf-8-sig',newline='') as stream:
        assert list(csv.reader(stream)) == [list(original)+['Country_Code','Zone_Code','NOVSN_Zone_Code'],
            ['original','keep-zone','keep-novsn','HK','LOCAL','A']]


def test_empty_report_has_new_schema_and_pinned_mapping(tmp_path):
    report = write_country_reports(iter([]),tmp_path,catalogue(),{},original_columns=['Address'])
    with (tmp_path/'Classified_Addresses.csv').open(encoding='utf-8-sig',newline='') as stream:
        assert next(csv.reader(stream)) == ['Address','Country_Code','Zone_Code','NOVSN_Zone_Code']
    assert report['total_records'] == 0 and report['report_schema_version'] == 2


def test_known_country_missing_from_mapping_does_not_publish(tmp_path):
    entry = SimpleNamespace(code='ZZ',name_en='synthetic',name_tc='synthetic',aliases=())
    with pytest.raises(ValueError):
        write_country_reports(iter([pair(1,'ZZ','INFERRED')]),tmp_path,
                              SimpleNamespace(entries={'ZZ':entry}),{})
    assert not (tmp_path/'Run_Manifest.json').exists()


def test_new_case_reader_and_export_use_derived_positions(tmp_path):
    from world_address_engine.gui.country_cases import load_case_page, export_cases
    output = tmp_path/'completed'
    write_country_reports(iter([pair(1,'HK','INFERRED',{'Address':'synthetic','Country_Code':'original'}),
                               pair(2,None,'UNRESOLVED',{'Address':'other','Country_Code':'original'})]),
                          output,catalogue(),{'address_columns':['Address']})
    rows = load_case_page(output,mode='all')['rows']
    assert [(r['code'],r['zone_code'],r['novsn_zone_code']) for r in rows] == [('HK','LOCAL','A'),('','','')]
    assert rows[0]['address'] == 'synthetic'
    target = tmp_path/'case-export.csv'
    assert export_cases(output,target,mode='all') == 2
    exported = read(target)
    assert exported[0]['Zone_Code'] == 'LOCAL' and exported[0]['NOVSN_Zone_Code'] == 'A'


def test_legacy_cases_remain_readonly_with_blank_zone_fields(tmp_path):
    from tests.unit.test_country_cases import published
    from world_address_engine.gui.country_cases import load_case_page
    output = published(tmp_path)
    before = {p.name:p.read_bytes() for p in output.iterdir()}
    rows = load_case_page(output,mode='all')['rows']
    assert all(r['zone_code'] == r['novsn_zone_code'] == '' for r in rows)
    assert before == {p.name:p.read_bytes() for p in output.iterdir()}


def test_unknown_report_schema_is_not_guessed_from_last_cell(tmp_path):
    from tests.unit.test_country_cases import published
    from world_address_engine.gui.country_cases import load_case_page
    output = published(tmp_path)
    path = output/'Run_Manifest.json'
    report = json.loads(path.read_text('utf8'))
    report['report_schema_version'] = 999
    path.write_text(json.dumps(report),encoding='utf8')
    with pytest.raises(ValueError,match='schema'):
        load_case_page(output,mode='all')
