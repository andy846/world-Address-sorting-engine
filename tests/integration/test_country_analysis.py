"""Synthetic-only integration coverage for country analysis orchestration."""
import csv
import hashlib
import importlib
import json

import pytest

from tests.unit.test_retrieve import geo


def runner():
    return importlib.import_module('world_address_engine.jobs.country_analysis')


def source(path, addresses=('Japan', '', 'India', 'Japan')):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Control no', 'NAME_ADDRESS_LINE1', '', 'Extra', 'Extra'])
        for number, address in enumerate(addresses, 1):
            writer.writerow([f'{number:06d}', address, '=2+2', 'left', 'right'])
    return path


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def test_analysis_streams_originals_and_counts_without_hkp(tmp_path):
    job = runner()
    data = source(tmp_path / 'synthetic.csv')
    out = tmp_path / 'out'
    progress = []
    manifest = job.analyze_job(data, out, geo(tmp_path), batch_size=2,
                               on_progress=progress.append)
    assert manifest['total_records'] == 4
    assert manifest['destination_counts'] == {'IN': 1, 'JP': 2}
    assert manifest['status_counts']['UNRESOLVED'] == 1
    assert sum(manifest['status_counts'].values()) == 4
    rows = read(out / 'Classified_Addresses.csv')
    assert list(rows[0]) == ['Control no', 'NAME_ADDRESS_LINE1', 'Unnamed_1',
                             'Extra', 'Extra_2', 'Country_Code', 'Zone_Code', 'NOVSN_Zone_Code']
    assert [r['Control no'] for r in rows] == ['000001', '000002', '000003', '000004']
    assert [r['Country_Code'] for r in rows] == ['JP', '', 'IN', 'JP']
    assert rows[0]['Unnamed_1'] == "'=2+2"
    assert progress == [2, 4]
    assert not (out / '.country-state').exists()
    metadata = manifest['run_metadata']
    for field in ('rules_version', 'catalogue_version', 'catalogue_fingerprint',
                  'catalogue_sha256', 'input_sha256', 'geo_sha256', 'profile',
                  'input_options_sha256'):
        assert metadata[field]
    assert metadata['profile'] == 'EXTENDED_GLOBAL'
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(FileExistsError):
        job.analyze_job(data, out, tmp_path / 'missing-geo.db')
    with pytest.raises(FileExistsError):
        job.resume_analysis(out)
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}


def test_pause_and_resume_keep_duplicate_rows_without_duplicate_output(tmp_path):
    job = runner()
    data = source(tmp_path / 'synthetic.csv', ['Japan'] * 5)
    out = tmp_path / 'out'
    paused = job.analyze_job(data, out, geo(tmp_path), batch_size=2, max_batches=1)
    assert paused['run_status'] == 'PAUSED' and paused['committed_records'] == 2
    assert not (out / 'Run_Manifest.json').exists()
    assert not (out / '.job-state').exists()
    assert job.resume_analysis(out, max_batches=1)['committed_records'] == 4
    manifest = job.resume_analysis(out, keep_checkpoint=True)
    assert manifest['destination_counts'] == {'JP': 5}
    assert len(read(out / 'Classified_Addresses.csv')) == 5
    assert (out / '.country-state').is_dir()


def test_cancel_before_first_batch_is_resumable(tmp_path):
    job = runner()
    data = source(tmp_path / 'synthetic.csv')
    out = tmp_path / 'out'
    result = job.analyze_job(data, out, geo(tmp_path), cancel_requested=lambda: True)
    assert result['run_status'] == 'CANCELLED'
    assert result['committed_records'] == 0
    assert not (out / 'Run_Manifest.json').exists()
    assert job.resume_analysis(out)['total_records'] == 4


@pytest.mark.parametrize('change', ['source', 'pack', 'options', 'rules', 'catalogue'])
def test_resume_rejects_changed_inputs_and_versions(tmp_path, change):
    job = runner()
    data = source(tmp_path / 'synthetic.csv')
    pack = geo(tmp_path)
    out = tmp_path / 'out'
    job.analyze_job(data, out, pack, batch_size=1, max_batches=1)
    config_path = out / '.country-state' / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf8'))
    if change == 'source':
        data.write_text('changed', encoding='utf8')
    elif change == 'pack':
        with pack.open('ab') as stream:
            stream.write(b'changed')
    elif change == 'options':
        config['input_options']['encoding'] = 'ascii'
    elif change == 'rules':
        config['rules_version'] = 'old-rules'
    else:
        config['catalogue_fingerprint'] = 'changed'
    config_path.write_text(json.dumps(config), encoding='utf8')
    with pytest.raises(ValueError, match='changed|version|profile|catalogue'):
        job.resume_analysis(out)
    assert not (out / 'Run_Manifest.json').exists()


def rewrite_shard(out, edit):
    shard = next((out / '.country-state').glob('*.jsonl'))
    payloads = [json.loads(line) for line in shard.read_text(encoding='utf8').splitlines()]
    edit(payloads)
    shard.write_text(''.join(json.dumps(p) + '\n' for p in payloads), encoding='utf8')
    start, end, _ = shard.stem.split('-')
    shard.rename(shard.with_name(f'{start}-{end}-{hashlib.sha256(shard.read_bytes()).hexdigest()}.jsonl'))


@pytest.mark.parametrize('part', ['record', 'result', 'tail', 'bounds'])
def test_rehashed_checkpoint_tampering_is_rejected(tmp_path, part):
    job = runner()
    data = source(tmp_path / 'synthetic.csv', ['Japan', 'India'])
    out = tmp_path / 'out'
    job.analyze_job(data, out, geo(tmp_path), batch_size=2, max_batches=1)

    def forge(payloads):
        if part == 'record':
            payloads[1]['record']['fields']['Control no'] = '999999'
        elif part == 'result':
            payloads[1]['result']['reason'] = 'FORGED_REASON'
        elif part == 'tail':
            payloads.pop()
        else:
            payloads[0]['checkpoint_header']['end'] = 1

    rewrite_shard(out, forge)
    with pytest.raises(ValueError, match='checkpoint|verification|source'):
        job.resume_analysis(out)
    assert not (out / 'Run_Manifest.json').exists()


def test_failure_after_committed_progress_can_resume(tmp_path):
    job = runner()
    data = source(tmp_path / 'synthetic.csv')
    out = tmp_path / 'out'

    def interrupted(_):
        raise RuntimeError('synthetic interruption')

    with pytest.raises(RuntimeError, match='interruption'):
        job.analyze_job(data, out, geo(tmp_path), batch_size=2, on_progress=interrupted)
    assert job.resume_analysis(out)['total_records'] == 4


def test_cleanup_failure_does_not_publish_manifest(tmp_path, monkeypatch):
    job = runner()
    data = source(tmp_path / 'synthetic.csv')
    out = tmp_path / 'out'

    def refuse(_):
        raise OSError('synthetic cleanup failure')

    monkeypatch.setattr(job, '_remove_checkpoint', refuse)
    with pytest.raises(OSError, match='cleanup failure'):
        job.analyze_job(data, out, geo(tmp_path))
    assert not (out / 'Run_Manifest.json').exists()
    assert (out / '.country-state').is_dir()


@pytest.mark.parametrize('kind', ['txt', 'xlsx', 'empty_csv'])
def test_other_input_formats_and_empty_csv(tmp_path, kind):
    job = runner()
    options = {}
    data = tmp_path / ('synthetic.xlsx' if kind == 'xlsx' else 'synthetic.txt')
    if kind == 'xlsx':
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.title = 'Synthetic'
        sheet.append(['ID', 'Address'])
        sheet.append(['000007', 'Japan'])
        book.save(data)
        book.close()
        options = {'sheet_name': 'Synthetic', 'address_columns': ['Address'],
                   'record_id_column': 'ID'}
    elif kind == 'txt':
        data.write_text('Japan\nIndia\n', encoding='utf8')
    else:
        data = source(tmp_path / 'empty.csv', [])
    out = tmp_path / 'out'
    manifest = job.analyze_job(data, out, geo(tmp_path), options)
    assert manifest['total_records'] == {'txt': 2, 'xlsx': 1, 'empty_csv': 0}[kind]
    if kind == 'xlsx':
        assert read(out / 'Classified_Addresses.csv')[0]['ID'] == '000007'
    if kind == 'empty_csv':
        with (out / 'Classified_Addresses.csv').open(encoding='utf-8-sig') as stream:
            assert next(csv.reader(stream)) == ['Control no', 'NAME_ADDRESS_LINE1',
                                               'Unnamed_1', 'Extra', 'Extra_2', 'Country_Code',
                                               'Zone_Code', 'NOVSN_Zone_Code']


def test_cli_analyze_and_resume_auto_detect_analysis(tmp_path, capsys):
    from world_address_engine.cli import main
    data = source(tmp_path / 'synthetic.csv')
    pack = geo(tmp_path)
    out = tmp_path / 'out'
    assert main(['analyze', '--input', str(data), '--output', str(out),
                 '--geo-db', str(pack), '--batch-size', '2', '--max-batches', '1']) == 0
    assert json.loads(capsys.readouterr().out)['run_status'] == 'PAUSED'
    assert main(['resume', '--job-dir', str(out)]) == 0
    assert json.loads(capsys.readouterr().out)['job_kind'] == 'country-analysis'


def test_variable_width_delimited_txt_preserves_all_original_fields(tmp_path):
    job = runner()
    data = tmp_path / 'synthetic.txt'
    data.write_text('Japan\nIndia|0007|=synthetic\nJapan|0008\n', encoding='utf8')
    out = tmp_path / 'out'
    job.analyze_job(data, out, geo(tmp_path), {'txt_mode': 'delimited', 'delimiter': '|'},
                    batch_size=1, max_batches=1)
    manifest = job.resume_analysis(out)
    assert manifest['total_records'] == 3
    assert read(out / 'Classified_Addresses.csv') == [
        {'Text_1': 'Japan', 'Text_2': '', 'Text_3': '', 'Country_Code': 'JP',
         'Zone_Code': '2', 'NOVSN_Zone_Code': 'D'},
        {'Text_1': 'India', 'Text_2': '0007', 'Text_3': "'=synthetic", 'Country_Code': 'IN',
         'Zone_Code': '1', 'NOVSN_Zone_Code': 'C'},
        {'Text_1': 'Japan', 'Text_2': '0008', 'Text_3': '', 'Country_Code': 'JP',
         'Zone_Code': '2', 'NOVSN_Zone_Code': 'D'},
    ]


def test_stop_after_a_batch_does_not_parse_the_rest_of_the_input(tmp_path, monkeypatch):
    job = runner()
    data = source(tmp_path / 'synthetic.csv', ['Japan'] * 12)
    out = tmp_path / 'out'
    actual_records = job._records
    parsed = 0

    def guarded(*args):
        nonlocal parsed
        for record in actual_records(*args):
            parsed += 1
            if parsed > 2:
                pytest.fail('analysis pre-read records beyond the batch limit')
            yield record

    monkeypatch.setattr(job, '_records', guarded)
    assert job.analyze_job(data, out, geo(tmp_path), batch_size=2,
                           max_batches=1)['committed_records'] == 2
    assert parsed == 2


def test_export_rechecks_shard_bytes_and_source_before_manifest(tmp_path, monkeypatch):
    job = runner()
    data = source(tmp_path / 'synthetic.csv', ['Japan'])
    out = tmp_path / 'out'
    job.analyze_job(data, out, geo(tmp_path), batch_size=1, max_batches=1)
    actual_write = job.write_country_reports

    def tamper_then_write(*args, **kwargs):
        shard = next((out / '.country-state').glob('*.jsonl'))
        shard.write_bytes(shard.read_bytes().replace(b'000001', b'999999'))
        return actual_write(*args, **kwargs)

    monkeypatch.setattr(job, 'write_country_reports', tamper_then_write)
    with pytest.raises(ValueError, match='source|verification|checkpoint'):
        job.resume_analysis(out)
    assert not (out / 'Run_Manifest.json').exists()


def test_mid_export_source_change_blocks_completion(tmp_path, monkeypatch):
    job = runner()
    data = source(tmp_path / 'synthetic.csv')
    out = tmp_path / 'out'
    actual_write = job.write_country_reports

    def write_then_mutate(items, output, catalogue, metadata, **kwargs):
        original_hook = kwargs['before_manifest']

        def changed_source():
            with data.open('a', encoding='utf8') as stream:
                stream.write('changed\n')
            original_hook()

        kwargs['before_manifest'] = changed_source
        return actual_write(items, output, catalogue, metadata, **kwargs)

    monkeypatch.setattr(job, 'write_country_reports', write_then_mutate)
    with pytest.raises(ValueError, match='input changed'):
        job.analyze_job(data, out, geo(tmp_path))
    assert not (out / 'Run_Manifest.json').exists()
    assert (out / '.country-state').is_dir()


@pytest.mark.parametrize('mode', ['error', 'cancel'])
def test_export_closes_source_and_checkpoint_generators_on_early_exit(tmp_path, monkeypatch, mode):
    job = runner()
    data = source(tmp_path / 'synthetic.csv')
    out = tmp_path / 'out'
    retained = []
    cancelled = False
    actual_records, actual_saved = job._records, job._saved_pairs

    def track_records(*args):
        iterator = actual_records(*args)
        retained.append(iterator)
        return iterator

    def track_saved(*args):
        iterator = actual_saved(*args)
        retained.append(iterator)
        return iterator

    def interrupted_report(items, *args, **kwargs):
        nonlocal cancelled
        retained.append(items)
        next(items)
        if mode == 'error':
            raise RuntimeError('synthetic export error')
        cancelled = True
        next(items)

    monkeypatch.setattr(job, '_records', track_records)
    monkeypatch.setattr(job, '_saved_pairs', track_saved)
    monkeypatch.setattr(job, 'write_country_reports', interrupted_report)
    if mode == 'error':
        with pytest.raises(RuntimeError, match='export error'):
            job.analyze_job(data, out, geo(tmp_path))
    else:
        assert job.analyze_job(data, out, geo(tmp_path),
                               cancel_requested=lambda: cancelled)['run_status'] == 'CANCELLED'
    assert all(iterator.gi_frame is None for iterator in retained)


def test_private_directory_changes_are_confined_to_state_and_report_staging(tmp_path, monkeypatch):
    job = runner()
    reports = importlib.import_module('world_address_engine.io.country_reports')
    data = source(tmp_path / 'synthetic.csv')
    out = tmp_path / 'out'
    actual_private = reports._private_directory
    protected = []

    def protect(path):
        resolved = path.resolve()
        assert resolved.parent == out.resolve()
        assert path.name in {'.country-state', '.country-finalize'} or path.name.startswith('.country-report-')
        protected.append(path.name)
        actual_private(path)

    monkeypatch.setattr(job, '_private_directory', protect)
    monkeypatch.setattr(reports, '_private_directory', protect)
    assert job.analyze_job(data, out, geo(tmp_path))['run_status'] == 'COMPLETE'
    assert sorted(name for name in protected if not name.startswith('.country-report-')) == [
        '.country-finalize', '.country-state']


@pytest.mark.parametrize('via_cli', [False, True])
def test_manifest_write_failure_keeps_metadata_only_recovery_and_can_resume(
        tmp_path, monkeypatch, capsys, via_cli):
    job = runner()
    reports = importlib.import_module('world_address_engine.io.country_reports')
    data = source(tmp_path / 'synthetic.csv', ['Japan', 'India'])
    data.write_text(data.read_text(encoding='utf-8-sig').replace(
        '=2+2', 'SYNTHETIC_PRIVATE_RECIPIENT'), encoding='utf-8-sig')
    out = tmp_path / 'out'
    original_config = None
    actual_remove = job._remove_checkpoint

    def capture_then_remove(state):
        nonlocal original_config
        original_config = json.loads((state / 'config.json').read_text(encoding='utf8'))
        actual_remove(state)

    def fail_manifest(*args):
        assert not (out / '.country-state').exists()
        raise OSError('synthetic manifest I/O failure')

    with monkeypatch.context() as patch:
        patch.setattr(job, '_remove_checkpoint', capture_then_remove)
        patch.setattr(reports, '_write_manifest_atomic', fail_manifest)
        with pytest.raises(OSError, match='manifest I/O failure'):
            job.analyze_job(data, out, geo(tmp_path), batch_size=1)
    assert not (out / 'Run_Manifest.json').exists()
    assert not (out / '.country-state').exists()
    recovery = out / '.country-finalize'
    assert recovery.is_dir()
    assert [path.name for path in recovery.iterdir()] == ['config.json']
    raw = (recovery / 'config.json').read_text(encoding='utf8')
    assert json.loads(raw) == original_config
    for private_text in ('SYNTHETIC_PRIVATE_RECIPIENT', 'address_text', 'evidence',
                         'country_hint', 'record_no', '=2+2'):
        assert private_text not in raw
    # A retry must derive outputs again rather than trust the failed publication.
    (out / 'Classified_Addresses.csv').write_text('forged stale report', encoding='utf8')
    if via_cli:
        from world_address_engine.cli import main
        assert main(['resume', '--job-dir', str(out)]) == 0
        manifest = json.loads(capsys.readouterr().out)
    else:
        manifest = job.resume_analysis(out)
    assert manifest['run_status'] == 'COMPLETE'
    assert manifest['total_records'] == 2
    assert manifest['destination_counts'] == {'IN': 1, 'JP': 1}
    assert [row['Control no'] for row in read(out / 'Classified_Addresses.csv')] == ['000001', '000002']
    assert not (out / '.country-state').exists()
    assert not recovery.exists()


@pytest.mark.parametrize('change', ['source', 'pack', 'options', 'rules', 'catalogue', 'profile'])
def test_finalization_recovery_preserves_source_and_version_checks(tmp_path, monkeypatch, change):
    job = runner()
    reports = importlib.import_module('world_address_engine.io.country_reports')
    data = source(tmp_path / 'synthetic.csv')
    pack = geo(tmp_path)
    out = tmp_path / 'out'

    def fail_manifest(*args):
        raise OSError('synthetic manifest I/O failure')

    with monkeypatch.context() as patch:
        patch.setattr(reports, '_write_manifest_atomic', fail_manifest)
        with pytest.raises(OSError, match='manifest I/O failure'):
            job.analyze_job(data, out, pack)
    config_path = out / '.country-finalize' / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf8'))
    if change == 'source':
        data.write_text('changed', encoding='utf8')
    elif change == 'pack':
        with pack.open('ab') as stream:
            stream.write(b'changed')
    elif change == 'options':
        config['input_options']['encoding'] = 'ascii'
    elif change == 'rules':
        config['rules_version'] = 'old-rules'
    elif change == 'profile':
        config['profile'] = 'changed'
    else:
        config['catalogue_fingerprint'] = 'changed'
    config_path.write_text(json.dumps(config), encoding='utf8')
    with pytest.raises(ValueError, match='changed|version|profile|catalogue'):
        job.resume_analysis(out)
    assert not (out / 'Run_Manifest.json').exists()
    assert not (out / '.country-state').exists()
