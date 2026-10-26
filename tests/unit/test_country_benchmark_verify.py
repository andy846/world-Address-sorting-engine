"""Synthetic-only corruption tests for the independent streaming verifier."""
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tracemalloc
from collections import Counter

import pytest

from tests.unit.test_retrieve import geo
from world_address_engine.jobs.country_analysis import analyze_job
from world_address_engine.io.reports import _protect


ZONE_IDENTITY = {'version': 'synthetic-zones-1', 'source_sha256': 'a' * 64,
                 'sha256': 'b' * 64}


@pytest.fixture
def schema2_case(tmp_path):
    """Literal reports independent of the application writer and zone lookup."""
    source = tmp_path / 'source.csv'
    output = tmp_path / 'out'
    output.mkdir()
    block = [
        {'fields': {'Address': 'Public HK', 'Country_Code': 'original'},
         'code': 'HK', 'status': 'DETERMINED', 'reason': 'EXPLICIT_COUNTRY',
         'candidates': [], 'zone_code': 'LOCAL', 'novsn_zone_code': 'A'},
        {'fields': {'Address': '', 'Country_Code': ''}, 'code': None,
         'status': 'UNRESOLVED', 'reason': 'EMPTY_ADDRESS', 'candidates': [],
         'zone_code': '', 'novsn_zone_code': ''}]
    write(source, [['Address', 'Country_Code', '_Benchmark_Cycle', '_Benchmark_Base_Row'],
                   ['Public HK', 'original', '1', '1'], ['', '', '1', '2']])
    write(output / 'Classified_Addresses.csv', [
        ['Address', 'Country_Code', '_Benchmark_Cycle', '_Benchmark_Base_Row',
         'Country_Code', 'Zone_Code', 'NOVSN_Zone_Code'],
        ['Public HK', 'original', '1', '1', 'HK', 'LOCAL', 'A'],
        ['', '', '1', '2', '', '', '']])
    write(output / 'Country_Diagnostics.csv', [
        ['Source_Record_No', 'Status', 'Reason', 'Candidates'],
        ['1', 'DETERMINED', 'EXPLICIT_COUNTRY', ''],
        ['2', 'UNRESOLVED', 'EMPTY_ADDRESS', '']])
    write(output / 'Country_Summary.csv', [
        ['Country_Code', 'Country_Name_TC', 'Country_Name_EN', 'Zone_Code',
         'NOVSN_Zone_Code', 'Count', 'Percentage'],
        ['HK', '香港', 'Hong Kong', 'LOCAL', 'A', '1', '50.00'],
        ['', '', '', '', '', '1', '50.00']])
    manifest = {
        'report_schema_version': 2,
        'generated_columns': ['Country_Code', 'Zone_Code', 'NOVSN_Zone_Code'],
        'run_status': 'COMPLETE', 'job_kind': 'country-analysis',
        'data_class': 'COUNTRY_CODE_ESTIMATE', 'total_records': 2,
        'status_counts': {'DETERMINED': 1, 'INFERRED': 0, 'UNRESOLVED': 1},
        'destination_counts': {'HK': 1},
        'run_metadata': {'zone_mapping': dict(ZONE_IDENTITY)},
        'files': ['Classified_Addresses.csv', 'Country_Summary.csv', 'Country_Diagnostics.csv']}
    (output / 'Run_Manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    rehash(source, output)
    return source, output, block


def test_schema2_verifies_literal_reports_against_pinned_zone_pairs(schema2_case):
    source, output, block = schema2_case
    assert verifier()(source, output, block, 1)['verified']


@pytest.mark.parametrize('filename,index,column,value', [
    ('Classified_Addresses.csv', 1, -2, 'CN - Airmail'),
    ('Classified_Addresses.csv', 1, -3, 'JP'),
    ('Classified_Addresses.csv', 2, -1, 'A'),
    ('Country_Summary.csv', 1, 3, 'OTHER'),
    ('Country_Summary.csv', 1, 4, 'F'),
    ('Country_Summary.csv', 2, 3, 'LOCAL'),
    ('Country_Summary.csv', 1, 5, '2'),
    ('Country_Summary.csv', 1, 6, '100.00')])
def test_schema2_rehashed_zone_and_count_corruption_fails(schema2_case, filename, index, column, value):
    source, output, block = schema2_case
    rows = read(output / filename)
    rows[index][column] = value
    write(output / filename, rows)
    rehash(source, output)
    with pytest.raises(ValueError):
        verifier()(source, output, block, 1, zone_mapping=ZONE_IDENTITY)


@pytest.mark.parametrize('damage', ['schema', 'tail', 'identity', 'identity_version',
                                    'identity_source', 'missing_identity',
                                    'oracle_pair', 'blank_known', 'unknown_pair'])
def test_schema2_requires_explicit_schema_identity_and_complete_oracle(schema2_case, damage):
    source, output, block = schema2_case
    path = output / 'Run_Manifest.json'
    manifest = json.loads(path.read_text(encoding='utf8'))
    if damage == 'schema':
        del manifest['report_schema_version']
    elif damage == 'tail':
        manifest['generated_columns'] = ['Country_Code']
    elif damage == 'identity':
        manifest['run_metadata']['zone_mapping']['sha256'] = 'c' * 64
    elif damage == 'identity_version':
        manifest['run_metadata']['zone_mapping']['version'] = 'other'
    elif damage == 'identity_source':
        manifest['run_metadata']['zone_mapping']['source_sha256'] = 'c' * 64
    elif damage == 'missing_identity':
        del manifest['run_metadata']['zone_mapping']
    elif damage == 'oracle_pair':
        del block[0]['zone_code']
    elif damage == 'blank_known':
        block[0]['zone_code'] = ''
    else:
        block[1]['novsn_zone_code'] = 'A'
    path.write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError):
        verifier()(source, output, block, 1, zone_mapping=ZONE_IDENTITY)


def verifier():
    path = Path(__file__).resolve().parents[2] / 'tools/country_benchmark_verify.py'
    assert path.is_file(), 'independent benchmark verifier is not implemented'
    spec = importlib.util.spec_from_file_location('benchmark_verifier_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_repeated_output


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.reader(stream))


def write(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        csv.writer(stream).writerows(rows)


def rehash(source, output):
    path = output / 'Run_Manifest.json'
    manifest = json.loads(path.read_text(encoding='utf8'))
    manifest['run_metadata']['input_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest['sha256'] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                          for name in manifest['files']}
    path.write_text(json.dumps(manifest), encoding='utf8')


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp('synthetic-benchmark-fixture')
    block = []
    samples = [('0001', 'Japan', 'JP', 'DETERMINED', 'EXPLICIT_COUNTRY', []),
               ('0001', 'Japan', 'JP', 'DETERMINED', 'EXPLICIT_COUNTRY', []),
               ('0002', '', None, 'UNRESOLVED', 'NO_ADDRESS_CONTEXT', []),
               ('0003', 'Japan\nIndia', None, 'UNRESOLVED',
                'CONFLICTING_COUNTRIES', ['IN', 'JP'])]
    for identifier, address, code, status, reason, candidates in samples:
        block.append({'fields': {'ID': identifier, 'Address': address,
                                '=Formula header': '=2+2\nsynthetic',
                                'Country_Code': 'ZZ', 'Note': '\t@synthetic'},
                      'code': code, 'status': status, 'reason': reason,
                      'candidates': candidates})
    source = root / 'synthetic.csv'
    rows = [list(block[0]['fields']) + ['_Benchmark_Cycle', '_Benchmark_Base_Row']]
    for cycle in range(1, 4):
        rows.extend([list(item['fields'].values()) + [str(cycle), str(index)]
                     for index, item in enumerate(block, 1)])
    write(source, rows)
    output = root / 'out'
    manifest = analyze_job(source, output, geo(root),
                           {'address_columns': ['Address']}, batch_size=5)
    from world_address_engine.data.zone_mappings import load_zone_mappings, zone_values
    zones = load_zone_mappings()
    for item in block:
        item['zone_code'], item['novsn_zone_code'] = zone_values(item['code'], zones)
    assert manifest['status_counts'] == {'DETERMINED': 6, 'INFERRED': 0, 'UNRESOLVED': 6}
    return root, block


@pytest.fixture
def case(prepared, tmp_path):
    root, block = prepared
    source = tmp_path / 'synthetic.csv'
    shutil.copyfile(root / source.name, source)
    output = tmp_path / 'out'
    shutil.copytree(root / 'out', output)
    return source, output, copy.deepcopy(block)


def test_real_runner_output_is_verified_without_writes_or_private_values(case, capsys):
    source, output, block = case
    before = {path: path.read_bytes() for path in [source, *output.iterdir()]}
    result = verifier()(source, output, block, 3)
    assert result['verified'] is True
    assert result['total_records'] == 12
    assert result['block_records'] == 4 and result['repeats'] == 3
    assert result['destination_counts'] == {'JP': 6}
    assert result['country_counts'] == {'': 6, 'JP': 6}
    assert result['status_counts'] == {'DETERMINED': 6, 'INFERRED': 0, 'UNRESOLVED': 6}
    assert len(result['source_sha256']) == 64
    assert set(result['sha256']) == {'Classified_Addresses.csv', 'Country_Summary.csv',
                                     'Country_Diagnostics.csv'}
    public = json.dumps(result)
    assert all(value not in public for value in ['synthetic', '=2+2', '0001', 'ZZ', str(source)])
    assert capsys.readouterr() == ('', '')
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize('filename', ['source', 'Classified_Addresses.csv', 'Country_Diagnostics.csv'])
@pytest.mark.parametrize('damage', ['truncate', 'extra', 'swap', 'extra_header', 'short_row', 'long_row'])
def test_rehashed_row_shape_count_and_order_corruption_is_rejected(case, filename, damage):
    source, output, block = case
    path = source if filename == 'source' else output / filename
    rows = read(path)
    if damage == 'truncate':
        rows.pop()
    elif damage == 'extra':
        rows.append(rows[-1])
    elif damage == 'swap':
        rows[2], rows[3] = rows[3], rows[2]
    elif damage == 'extra_header':
        rows[0].append('Extra')
    elif damage == 'short_row':
        rows[1].pop()
    else:
        rows[1].append('Extra')
    write(path, rows)
    rehash(source, output)
    with pytest.raises(ValueError):
        verifier()(source, output, block, 3)


@pytest.mark.parametrize('filename,column,value', [
    ('source', 0, 'PRIVATE_MARKER'), ('source', 5, '01'), ('source', 6, '0'),
    ('Classified_Addresses.csv', 2, '=2+2\nsynthetic'),
    ('Classified_Addresses.csv', -1, 'ZZ'),
    ('Classified_Addresses.csv', 3, 'JP'),
    ('Country_Diagnostics.csv', 0, '01'), ('Country_Diagnostics.csv', 1, 'INFERRED'),
    ('Country_Diagnostics.csv', 2, 'PRIVATE_MARKER'),
    ('Country_Diagnostics.csv', 3, 'JP'),
])
def test_rehashed_cell_tampering_is_rejected_without_exposing_values(case, filename, column, value):
    source, output, block = case
    path = source if filename == 'source' else output / filename
    rows = read(path)
    rows[1][column] = value
    write(path, rows)
    rehash(source, output)
    with pytest.raises(ValueError) as caught:
        verifier()(source, output, block, 3)
    assert 'PRIVATE_MARKER' not in str(caught.value)


@pytest.mark.parametrize('damage', ['count', 'percent', 'duplicate', 'missing_blank', 'header', 'extra_cell'])
def test_rehashed_summary_corruption_is_rejected(case, damage):
    source, output, block = case
    path = output / 'Country_Summary.csv'
    rows = read(path)
    if damage == 'count':
        rows[1][-2] = '7'
    elif damage == 'percent':
        rows[1][-1] = '100.00'
    elif damage == 'duplicate':
        rows.append(rows[1])
    elif damage == 'missing_blank':
        rows.pop()
    elif damage == 'header':
        rows[0][0] = 'Wrong'
    else:
        rows[1].append('extra')
    write(path, rows)
    rehash(source, output)
    with pytest.raises(ValueError):
        verifier()(source, output, block, 3)


@pytest.mark.parametrize('damage', ['status', 'job', 'data_class', 'count', 'counts',
                                    'destinations', 'files', 'hashes', 'source_hash'])
def test_manifest_must_attest_exact_contract(case, damage):
    source, output, block = case
    path = output / 'Run_Manifest.json'
    manifest = json.loads(path.read_text(encoding='utf8'))
    if damage == 'status':
        manifest['run_status'] = 'PAUSED'
    elif damage == 'job':
        manifest['job_kind'] = 'postal'
    elif damage == 'data_class':
        manifest['data_class'] = 'PRODUCTION_APPROVED'
    elif damage == 'count':
        manifest['total_records'] = 11
    elif damage == 'counts':
        manifest['status_counts']['DETERMINED'] = 7
    elif damage == 'destinations':
        manifest['destination_counts'] = {'ZZ': 6}
    elif damage == 'files':
        manifest['files'].append('../outside.csv')
    elif damage == 'hashes':
        manifest['sha256']['unexpected.csv'] = '0' * 64
    else:
        manifest['run_metadata']['input_sha256'] = '0' * 64
    path.write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError):
        verifier()(source, output, block, 3)


@pytest.mark.parametrize('filename', ['source', 'Classified_Addresses.csv',
                                     'Country_Summary.csv', 'Country_Diagnostics.csv'])
def test_hash_tampering_is_detected_when_all_parsed_rows_are_unchanged(case, filename):
    source, output, block = case
    path = source if filename == 'source' else output / filename
    before = read(path)
    original = path.read_bytes()
    changed = original.replace(b'\r\n', b'\n')
    assert original != changed
    path.write_bytes(changed)
    assert read(path) == before
    with pytest.raises(ValueError):
        verifier()(source, output, block, 3)


@pytest.mark.parametrize('repeats', [0, -1, True, 1.5])
def test_invalid_repeat_count_is_rejected(case, repeats):
    source, output, block = case
    with pytest.raises(ValueError):
        verifier()(source, output, block, repeats)


def test_wrong_oracle_count_or_schema_cannot_pass(case):
    source, output, block = case
    check = verifier()
    for invalid in [[], block[:-1], [dict(item, fields={'Wrong': ''}) for item in block]]:
        with pytest.raises(ValueError):
            check(source, output, invalid, 3)


def report_fixture(root, block, repeats):
    """Historical schema 1 fixture, independent of the current schema 2 writer."""
    block = [{key: value for key, value in item.items()
              if key not in ('zone_code', 'novsn_zone_code')} for item in block]
    source = root / 'synthetic-direct.csv'
    columns = list(block[0]['fields']) + ['_Benchmark_Cycle', '_Benchmark_Base_Row']

    def cells():
        for cycle in range(1, repeats + 1):
            for index, item in enumerate(block, 1):
                yield item, list(item['fields'].values()) + [str(cycle), str(index)]

    with source.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(values for _, values in cells())

    output = root / 'direct-output'
    output.mkdir()
    write(output / 'Classified_Addresses.csv', [
        [_protect(key) for key in columns] + ['Country_Code'],
        *[[_protect(value) for value in values] + [item['code'] or '']
          for item, values in cells()]])
    write(output / 'Country_Diagnostics.csv', [
        ['Source_Record_No', 'Status', 'Reason', 'Candidates'],
        *[[str(number), item['status'], _protect(item['reason']),
           _protect(';'.join(item['candidates']))]
          for number, (item, _) in enumerate(cells(), 1)]])
    counts = Counter()
    statuses = dict.fromkeys(['DETERMINED', 'INFERRED', 'UNRESOLVED'], 0)
    for item, _ in cells():
        counts[item['code'] or ''] += 1
        statuses[item['status']] += 1
    total = repeats * len(block)
    write(output / 'Country_Summary.csv', [
        ['Country_Code', 'Country_Name_TC', 'Country_Name_EN', 'Count', 'Percentage'],
        *[[code, code, code, str(count), f'{count * 100 / total:.2f}']
          for code, count in sorted(counts.items())]])
    manifest = {'run_status': 'COMPLETE', 'job_kind': 'country-analysis',
                'data_class': 'COUNTRY_CODE_ESTIMATE', 'total_records': total,
                'status_counts': statuses, 'destination_counts': {k: v for k, v in counts.items() if k},
                'run_metadata': {}, 'files': ['Classified_Addresses.csv', 'Country_Summary.csv',
                                             'Country_Diagnostics.csv']}
    (output / 'Run_Manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    rehash(source, output)
    return source, output


def test_inferred_codes_and_long_unicode_multiline_fields_are_preserved(tmp_path):
    block = [{'fields': {'Address': '東京\n' * 50000, '=Original': '+123'},
              'code': 'JP', 'status': 'INFERRED', 'reason': 'SYNTHETIC_INFERENCE',
              'candidates': ['JP', 'IN']}]
    source, output = report_fixture(tmp_path, block, 2)
    old_limit = csv.field_size_limit()
    result = verifier()(source, output, block, 2)
    assert result['country_counts'] == {'JP': 2}
    assert result['status_counts'] == {'DETERMINED': 0, 'INFERRED': 2, 'UNRESOLVED': 0}
    assert csv.field_size_limit() == old_limit


def test_large_repetition_is_streamed_without_retaining_all_rows(tmp_path, prepared):
    _, block = prepared
    block = [{key: value for key, value in item.items()
              if key not in ('zone_code', 'novsn_zone_code')} for item in block]
    source, output = report_fixture(tmp_path, block, 2000)
    check = verifier()
    tracemalloc.start()
    try:
        result = check(source, output, block, 2000)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result['total_records'] == 8000
    # Even this 8k workload requires many MB if csv rows are retained.
    assert peak < 1_500_000


def test_all_unresolved_summary_with_only_blank_code_is_valid(tmp_path):
    block = [{'fields': {'Address': ''}, 'code': None, 'status': 'UNRESOLVED',
              'reason': 'EMPTY_ADDRESS', 'candidates': []}]
    source, output = report_fixture(tmp_path, block, 2)
    result = verifier()(source, output, block, 2)
    assert result['destination_counts'] == {}
    assert result['country_counts'] == {'': 2}


@pytest.mark.parametrize('part', ['source', 'Classified_Addresses.csv', 'Country_Diagnostics.csv',
                                  'Country_Summary.csv', 'Run_Manifest.json'])
def test_missing_input_is_rejected_without_exposing_path(case, part):
    source, output, block = case
    target = source if part == 'source' else output / part
    target.rename(target.with_suffix('.unavailable'))
    with pytest.raises(ValueError) as caught:
        verifier()(source, output, block, 3)
    assert str(source.parent) not in str(caught.value)


@pytest.mark.parametrize('damage', ['field_order', 'collision', 'status', 'code', 'candidates'])
def test_invalid_or_inconsistent_oracle_is_rejected(case, damage):
    source, output, block = case
    if damage == 'field_order':
        block[1]['fields'] = dict(reversed(list(block[1]['fields'].items())))
    elif damage == 'collision':
        for item in block:
            item['fields']['_Benchmark_Cycle'] = '1'
    elif damage == 'status':
        block[0]['status'] = 'UNRESOLVED'
    elif damage == 'code':
        block[0]['code'] = 'PRIVATE_MARKER'
    else:
        block[0]['candidates'] = ['PRIVATE_MARKER']
    with pytest.raises(ValueError) as caught:
        verifier()(source, output, block, 3)
    assert 'PRIVATE_MARKER' not in str(caught.value)
