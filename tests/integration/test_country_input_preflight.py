"""Synthetic input failures must not leave country-analysis checkpoints."""
from contextlib import closing
import csv

from openpyxl import Workbook
import pytest

from tests.unit.test_retrieve import geo
from world_address_engine.jobs import country_analysis as job


def source(tmp_path, kind, headers, rows=()):
    path = tmp_path / ('synthetic.' + kind)
    if kind == 'csv':
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)
    else:
        book = Workbook()
        try:
            book.active.title = 'Synthetic'
            book.active.append(headers)
            for row in rows:
                book.active.append(row)
            book.save(path)
        finally:
            book.close()
    return path


@pytest.mark.parametrize('kind', ['csv', 'xlsx'])
@pytest.mark.parametrize('header_only', [False, True])
@pytest.mark.parametrize('issue', ['mapping', 'address', 'record_id'])
@pytest.mark.parametrize('existing_empty', [False, True])
def test_invalid_columns_leave_no_state_or_hashes(
        tmp_path, monkeypatch, kind, header_only, issue, existing_empty):
    data = source(tmp_path, kind, ['ID', 'Address'], [] if header_only else [['7', 'Japan']])
    options = {'sheet_name': 'Synthetic'} if kind == 'xlsx' else {}
    if issue == 'address':
        options['address_columns'] = ['Missing']
    elif issue == 'record_id':
        options.update(address_columns=['Address'], record_id_column='Missing')
    out = tmp_path / 'out'
    if existing_empty:
        out.mkdir()
    pack = geo(tmp_path)
    hashed = []
    actual_hash = job.file_sha256

    def track_hash(path):
        hashed.append(path)
        return actual_hash(path)

    monkeypatch.setattr(job, 'file_sha256', track_hash)
    for _ in range(2):
        with pytest.raises(ValueError, match='address column|record ID column'):
            job.analyze_job(data, out, pack, options)
        assert out.exists() is existing_empty
        assert not out.exists() or list(out.iterdir()) == []
        assert hashed == []


@pytest.mark.parametrize('sheet_name', [None, 'Missing'])
def test_missing_worksheet_leaves_no_output(tmp_path, sheet_name):
    data = source(tmp_path, 'xlsx', ['Address'], [['Japan']])
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='sheet_name|worksheet not found'):
        job.analyze_job(data, out, geo(tmp_path),
                        {'sheet_name': sheet_name, 'address_columns': ['Address']})
    assert not out.exists()


@pytest.mark.parametrize('kind', ['csv', 'xlsx'])
@pytest.mark.parametrize('empty', [False, True])
@pytest.mark.parametrize('standard', [False, True])
def test_valid_headers_and_empty_inputs_remain_supported(tmp_path, kind, empty, standard):
    header = 'NAME_ADDRESS_LINE1' if standard else 'Address'
    data = source(tmp_path, kind, ['ID', header], [] if empty else [['0007', 'Japan']])
    options = {'sheet_name': 'Synthetic'} if kind == 'xlsx' else {}
    if not standard:
        options.update(address_columns=['Address'], record_id_column='ID')
    out = tmp_path / 'out'
    result = job.analyze_job(data, out, geo(tmp_path), options)
    assert result['total_records'] == (0 if empty else 1)
    assert result['destination_counts'] == ({} if empty else {'JP': 1})
    with (out / 'Classified_Addresses.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert next(csv.reader(stream)) == ['ID', header, 'Country_Code', 'Zone_Code', 'NOVSN_Zone_Code']
    assert not (out / '.country-state').exists()


def test_formula_without_cached_value_remains_an_input_error_record(tmp_path):
    data = source(tmp_path, 'xlsx', ['NAME_ADDRESS_LINE1'], [['="Japan"']])
    out = tmp_path / 'out'
    result = job.analyze_job(data, out, geo(tmp_path), {'sheet_name': 'Synthetic'})
    assert result['total_records'] == 1
    assert result['status_counts']['UNRESOLVED'] == 1
    with (out / 'Country_Diagnostics.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert next(csv.DictReader(stream))['Reason'] == 'FORMULA_WITHOUT_CACHED_VALUE'


@pytest.mark.parametrize('options', [{'txt_mode': 'bad'}, {'txt_mode': 'delimited'}])
def test_invalid_txt_options_leave_no_output(tmp_path, options):
    data = tmp_path / 'synthetic.txt'
    data.write_text('Japan\n', encoding='utf8')
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='TXT'):
        job.analyze_job(data, out, geo(tmp_path), options)
    assert not out.exists()


@pytest.mark.parametrize('mode', ['line', 'delimited'])
def test_txt_behavior_is_preserved(tmp_path, mode):
    data = tmp_path / 'synthetic.txt'
    data.write_text('Japan\nIndia\n', encoding='utf8')
    result = job.analyze_job(data, tmp_path / 'out', geo(tmp_path),
                             {'txt_mode': mode, 'delimiter': '|'})
    assert result['total_records'] == 2
    assert result['destination_counts'] == {'JP': 1, 'IN': 1}


@pytest.mark.parametrize('stop', ['complete', 'pause', 'cancel'])
def test_record_generators_are_closed(tmp_path, monkeypatch, stop):
    data = source(tmp_path, 'csv', ['NAME_ADDRESS_LINE1'], [['Japan'], ['India']])
    actual_records = job._records
    active = []

    def tracked(*args):
        token = object()
        active.append(token)
        try:
            with closing(actual_records(*args)) as records:
                yield from records
        finally:
            active.remove(token)

    monkeypatch.setattr(job, '_records', tracked)
    options = {'batch_size': 1, 'max_batches': 1} if stop == 'pause' else {}
    if stop == 'cancel':
        options['cancel_requested'] = lambda: True
    job.analyze_job(data, tmp_path / 'out', geo(tmp_path), **options)
    assert active == []


def test_nonempty_output_still_refuses_new_job(tmp_path):
    data = source(tmp_path, 'csv', ['Address'], [['Japan']])
    out = tmp_path / 'out'
    out.mkdir()
    sentinel = out / 'keep.txt'
    sentinel.write_text('synthetic existing output', encoding='utf8')
    with pytest.raises(FileExistsError):
        job.analyze_job(data, out, geo(tmp_path))
    assert sentinel.read_text(encoding='utf8') == 'synthetic existing output'
    assert list(out.iterdir()) == [sentinel]
