"""Bounded, positional case views use synthetic published reports only."""
import csv
import hashlib
import json

import pytest


def published(tmp_path, rows=None):
    output = tmp_path / 'reports'
    output.mkdir()
    rows = rows if rows is not None else [
        ('JP', 'DETERMINED', 'EXPLICIT_COUNTRY', 'Tokyo Japan', ''),
        ('', 'UNRESOLVED', 'CONFLICTING_COUNTRIES', 'Japan\nIndia', 'IN;JP'),
        ('HK', 'INFERRED', 'GEOGRAPHIC_SUPPORT', 'Kowloon', 'HK'),
        ('', 'UNRESOLVED', 'FORMULA_WITHOUT_CACHED_VALUE', '=2+2', ''),
    ]
    with (output / 'Classified_Addresses.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['ID', 'Address', 'Country_Code', 'Country_Code'])
        writer.writerows([f'{i:04}', address, 'original-code', code]
                         for i, (code, status, reason, address, candidates) in enumerate(rows, 1))
    with (output / 'Country_Diagnostics.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Source_Record_No', 'Status', 'Reason', 'Candidates'])
        writer.writerows([i, status, reason, candidates]
                         for i, (code, status, reason, address, candidates) in enumerate(rows, 1))
    (output / 'Run_Manifest.json').write_text(json.dumps({
        'job_kind': 'country-analysis', 'run_status': 'COMPLETE', 'total_records': len(rows),
        'run_metadata': {'address_columns': ['Address']},
    }), encoding='utf-8')
    refresh_hashes(output)
    return output


def refresh_hashes(output):
    path = output / 'Run_Manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest['sha256'] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                          for name in ('Classified_Addresses.csv', 'Country_Diagnostics.csv')}
    path.write_text(json.dumps(manifest), encoding='utf-8')


def test_pending_default_pairs_logical_records_and_preserves_multiline(tmp_path):
    from world_address_engine.gui.country_cases import load_case_page
    page = load_case_page(published(tmp_path))
    assert [row['record_no'] for row in page['rows']] == [2, 4]
    assert page['rows'][0]['address'] == 'Japan\nIndia'
    assert page['rows'][0]['candidates'] == 'IN;JP'
    assert page['rows'][1]['reason'] == 'FORMULA_WITHOUT_CACHED_VALUE'
    assert all(row['code'] == '' for row in page['rows'])
    assert not page['has_next']


def test_filters_and_cursor_paging_are_bounded(tmp_path):
    from world_address_engine.gui.country_cases import load_case_page
    output = published(tmp_path)
    page = load_case_page(output, limit=1)
    assert len(page['rows']) == 1 and page['has_next']
    assert page['next_cursor'] == 2
    page = load_case_page(output, limit=1, after_record=page['next_cursor'])
    assert page['rows'][0]['record_no'] == 4 and not page['has_next']
    inferred = load_case_page(output, mode='inferred')
    assert [row['code'] for row in inferred['rows']] == ['HK']
    assert len(load_case_page(output, mode='all')['rows']) == 4


def test_empty_results_are_valid(tmp_path):
    from world_address_engine.gui.country_cases import load_case_page
    assert load_case_page(published(tmp_path, []))['rows'] == []


@pytest.mark.parametrize('damage', ['missing', 'reordered', 'short', 'wide', 'status', 'total'])
def test_mismatched_reports_fail_visibly(tmp_path, damage):
    from world_address_engine.gui.country_cases import load_case_page
    output = published(tmp_path)
    diagnostic = output / 'Country_Diagnostics.csv'
    with diagnostic.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    if damage == 'missing':
        diagnostic.unlink()
    elif damage == 'total':
        manifest = output / 'Run_Manifest.json'
        content = json.loads(manifest.read_text())
        content['total_records'] += 1
        manifest.write_text(json.dumps(content))
    else:
        if damage == 'reordered':
            rows[1], rows[2] = rows[2], rows[1]
        elif damage == 'short':
            rows.pop()
        elif damage == 'wide':
            rows[1].append('extra')
        elif damage == 'status':
            rows[1][1] = 'UNRESOLVED'
        with diagnostic.open('w', encoding='utf-8-sig', newline='') as stream:
            csv.writer(stream).writerows(rows)
    with pytest.raises((ValueError, OSError)):
        load_case_page(output, mode='all')


@pytest.mark.parametrize('kwargs', [{'limit': 0}, {'limit': 101}, {'after_record': -1}, {'mode': 'bad'}])
def test_reject_invalid_page_options(tmp_path, kwargs):
    from world_address_engine.gui.country_cases import load_case_page
    with pytest.raises(ValueError):
        load_case_page(published(tmp_path), **kwargs)


def test_cancellation_has_no_partial_result(tmp_path):
    from world_address_engine.gui.country_cases import CaseReadCancelled, load_case_page
    with pytest.raises(CaseReadCancelled):
        load_case_page(published(tmp_path), cancel_requested=lambda: True)


def test_export_streams_whole_filter_with_bom_formula_protection_and_no_mutation(tmp_path):
    from world_address_engine.gui.country_cases import export_cases
    output = published(tmp_path)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    target = tmp_path / 'pending.csv'
    assert export_cases(output, target) == 2
    assert target.read_bytes().startswith(b'\xef\xbb\xbf')
    with target.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]['Address'] == 'Japan\nIndia'
    assert rows[1]['Address'] == "'=2+2"
    assert [row['Source_Record_No'] for row in rows] == ['2', '4']
    with pytest.raises(FileExistsError):
        export_cases(output, target, mode='all')
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_export_cancel_failure_removes_staging_and_never_publishes(tmp_path):
    from world_address_engine.gui.country_cases import CaseReadCancelled, export_cases
    output = published(tmp_path)
    target = tmp_path / 'cancelled.csv'
    with pytest.raises(CaseReadCancelled):
        export_cases(output, target, cancel_requested=lambda: True)
    assert not target.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['reports']


def test_large_source_page_retains_only_requested_rows(tmp_path):
    from world_address_engine.gui.country_cases import load_case_page
    output = published(tmp_path, [('', 'UNRESOLVED', 'EMPTY_ADDRESS', '', '')] * 10_000)
    page = load_case_page(output)
    assert len(page['rows']) == 100 and page['has_next']
    assert page['next_cursor'] == 100


def test_formula_header_mapping_and_existing_country_code_are_positional(tmp_path):
    from world_address_engine.gui.country_cases import load_case_page
    output = published(tmp_path)
    target = output / 'Classified_Addresses.csv'
    text = target.read_text(encoding='utf-8-sig').replace('ID,Address,', "ID,'=Address,")
    target.write_text(text, encoding='utf-8-sig')
    refresh_hashes(output)
    page = load_case_page(output, mode='all', address_columns=('=Address', 'Country_Code'))
    assert page['rows'][0]['address'] == 'Tokyo Japan\noriginal-code'
    assert page['rows'][0]['code'] == 'JP'


def test_export_detects_destination_created_during_scan_without_overwriting(tmp_path, monkeypatch):
    from world_address_engine.gui import country_cases
    output = published(tmp_path)
    destination = tmp_path / 'raced.csv'
    original = country_cases._paired_cases

    def racing(*args, **kwargs):
        yield from original(*args, **kwargs)
        destination.write_text('existing user file', encoding='utf-8')

    monkeypatch.setattr(country_cases, '_paired_cases', racing)
    with pytest.raises(FileExistsError):
        country_cases.export_cases(output, destination)
    assert destination.read_text(encoding='utf-8') == 'existing user file'
    assert not list(tmp_path.glob('.wase-cases-*'))


def test_case_export_rejects_completed_output_subdirectory(tmp_path):
    from world_address_engine.gui.country_cases import export_cases
    output = published(tmp_path)
    with pytest.raises(ValueError, match='outside'):
        export_cases(output, output / 'new-case-export.csv')
    assert not (output / 'new-case-export.csv').exists()


def test_swapped_same_status_addresses_are_rejected_by_manifest_hash(tmp_path):
    from world_address_engine.gui.country_cases import export_cases, load_case_page
    output = published(tmp_path)
    detail = output / 'Classified_Addresses.csv'
    with detail.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    rows[2], rows[4] = rows[4], rows[2]
    with detail.open('w', encoding='utf-8-sig', newline='') as stream:
        csv.writer(stream).writerows(rows)
    with pytest.raises(ValueError, match='checksum'):
        load_case_page(output, limit=1)
    destination = tmp_path / 'must-not-publish.csv'
    with pytest.raises(ValueError, match='checksum'):
        export_cases(output, destination)
    assert not destination.exists()


def test_formula_protected_header_collision_fails_instead_of_exporting_id(tmp_path):
    from world_address_engine.gui.country_cases import load_case_page
    output = published(tmp_path)
    detail = output / 'Classified_Addresses.csv'
    text = detail.read_text(encoding='utf-8-sig').replace('ID,Address,', "'=Address,'=Address,")
    detail.write_text(text, encoding='utf-8-sig')
    refresh_hashes(output)
    with pytest.raises(ValueError, match='[Aa]mbiguous'):
        load_case_page(output, address_columns=('=Address',))


def test_real_long_txt_report_can_be_reviewed_and_exported(tmp_path):
    from tests.unit.test_retrieve import geo
    from world_address_engine.jobs.country_analysis import analyze_job
    from world_address_engine.gui.country_cases import export_cases, load_case_page
    source = tmp_path / 'long-synthetic.txt'
    source.write_text('x' * 150_000, encoding='utf-8')
    output = tmp_path / 'long-output'
    analyze_job(source, output, geo(tmp_path))
    page = load_case_page(output)
    assert len(page['rows'][0]['address']) == 150_000
    assert page['rows'][0]['reason'] == 'ADDRESS_TOO_LONG'
    assert export_cases(output, tmp_path / 'long-cases.csv') == 1
