"""Local-only repeated country-analysis benchmark. Never publish its workspace.

prepare preserves an input block, adds source-labelled public controls, and
repeats the WHOLE block. run/resume execute the ordinary application runner in
fresh processes. verify checks every row against the private one-block oracle.
Only the public tool/controls and aggregate receipts belong in Git or CI.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from itertools import zip_longest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))

from world_address_engine.io.country_reports import _private_directory
from world_address_engine.io.delimited import iter_csv_records, _record
from world_address_engine.io.reports import _protect
from world_address_engine.jobs.checkpoint import atomic_json, file_sha256
from world_address_engine.data.hk_regional import hk_pack_metadata
from world_address_engine.jobs.country_analysis import analyze_job, resume_analysis
from world_address_engine.matching.country import COUNTRY_RULES_VERSION, CountryClassifier

CYCLE = '_Benchmark_Cycle'
BASE_ROW = '_Benchmark_Base_Row'
FORBIDDEN = {CYCLE, BASE_ROW, 'Country_Code', 'Country', 'COUNTRY'}


def _read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream, strict=True)


def _oracle_item(fields, found):
    return {'fields': fields, 'code': found.country_code, 'status': found.status,
            'reason': found.reason, 'candidates': list(found.candidates)}


def _baseline_block(source, baseline, pack, hk_regional=None):
    manifest = json.loads((baseline / 'Run_Manifest.json').read_text(encoding='utf-8-sig'))
    metadata = manifest.get('run_metadata', {})
    if manifest.get('run_status') != 'COMPLETE' or manifest.get('job_kind') != 'country-analysis':
        raise ValueError('baseline is not a complete country analysis')
    if metadata.get('rules_version') != COUNTRY_RULES_VERSION:
        raise ValueError('baseline rules version changed')
    if metadata.get('input_sha256') != file_sha256(source):
        raise ValueError('baseline source hash changed')
    if metadata.get('geo_sha256') != file_sha256(pack):
        raise ValueError('baseline reference pack hash changed')
    if metadata.get('hk_regional') != hk_regional:
        raise ValueError('baseline regional selection changed')
    from world_address_engine.data.country_codes import load_country_codes
    from world_address_engine.jobs.country_analysis import _catalogue_metadata
    for key, value in _catalogue_metadata(load_country_codes()).items():
        if metadata.get(key) != value:
            raise ValueError('baseline country catalogue changed')
    for name in ('Classified_Addresses.csv', 'Country_Diagnostics.csv', 'Country_Summary.csv'):
        if file_sha256(baseline / name) != manifest.get('sha256', {}).get(name):
            raise ValueError('baseline report hash changed')
    columns = tuple(metadata.get('address_columns') or ())
    # Match the input reader's automatic subset when original files use fewer
    # than five standard columns. No inference hints may be added accidentally.
    records = iter_csv_records(source, 'utf-8-sig', tuple(metadata.get('address_columns') or ()))
    block = []
    for original, exported, diag in zip_longest(
            records, _read(baseline / 'Classified_Addresses.csv'), _read(baseline / 'Country_Diagnostics.csv')):
        if original is None or exported is None or diag is None:
            raise ValueError('baseline/source row count mismatch')
        if FORBIDDEN.intersection(original.fields):
            raise ValueError('benchmark source has a reserved metadata or trusted-hint column')
        if list(exported) != [*original.fields, 'Country_Code']:
            raise ValueError('baseline original columns changed')
        if any(exported[key] != _protect(value) for key, value in original.fields.items()):
            raise ValueError('baseline original field mismatch')
        if diag['Source_Record_No'] != str(original.record_no):
            raise ValueError('baseline record order mismatch')
        block.append({'fields': dict(original.fields), 'code': exported['Country_Code'] or None,
                      'status': diag['Status'], 'reason': diag['Reason'],
                      'candidates': diag['Candidates'].split(';') if diag['Candidates'] else []})
    if not block or len(block) != manifest['total_records']:
        raise ValueError('baseline source count mismatch or empty source')
    if not columns:
        columns = tuple(f'NAME_ADDRESS_LINE{i}' for i in range(1, 6)
                        if f'NAME_ADDRESS_LINE{i}' in block[0]['fields'])
    if not columns or not set(columns) <= set(block[0]['fields']):
        raise ValueError('address column mapping is missing')
    return block, columns, manifest


def prepare_workload(source, baseline, controls, workspace, pack, *, repeats=100, control_rows=396,
                     hk_regional_db=None):
    """Make a private copy without changing source values or original IDs."""
    source, baseline, controls, workspace, pack = map(
        lambda value: Path(value).resolve(), (source, baseline, controls, workspace, pack))
    if workspace.exists():
        raise FileExistsError('benchmark workspace already exists')
    if workspace.is_relative_to(baseline):
        raise ValueError('benchmark cannot write inside a completed baseline')
    if (isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1 or
            isinstance(control_rows, bool) or not isinstance(control_rows, int) or control_rows < 0):
        raise ValueError('repeat/control counts must be nonnegative integers, repeats positive')
    regional = hk_pack_metadata(hk_regional_db) if hk_regional_db is not None else None
    block, address_columns, manifest = _baseline_block(source, baseline, pack, regional)
    source_hash = file_sha256(source)
    baseline_hashes = {name: file_sha256(baseline / name) for name in
                       ('Run_Manifest.json', 'Classified_Addresses.csv', 'Country_Diagnostics.csv', 'Country_Summary.csv')}
    original_records = len(block)
    controls_hash = file_sha256(controls)
    public = json.loads(controls.read_text(encoding='utf-8'))
    pool = public.get('controls', [])
    if public.get('schema_version') != 1 or not pool:
        raise ValueError('public control source manifest missing')
    if len({c.get('control_id') for c in pool}) != len(pool):
        raise ValueError('duplicate public control identifier')
    with CountryClassifier(pack, hk_regional_db=hk_regional_db) as classifier:
        for index in range(control_rows):
            control = pool[index % len(pool)]
            if (not re.fullmatch('[A-Z]{2}', control.get('expected_code', '')) or
                    not control.get('source_url', '').startswith('https://') or
                    not control.get('lines') or len(control['lines']) > len(address_columns)):
                raise ValueError('public control source/label/address columns are invalid')
            fields = dict.fromkeys(block[0]['fields'], '')
            for column, line in zip(address_columns, control['lines']):
                fields[column] = line
            if 'Control no' in fields:
                fields['Control no'] = f'PUBLIC-BENCHMARK-{index + 1:06d}'
            rec = _record(original_records + index + 1, source, fields, address_columns)
            found = classifier.classify(rec)
            if found.country_code != control['expected_code']:
                raise ValueError('public control classification disagrees with its independent label')
            block.append(_oracle_item(fields, found))
    # All validity/control checks happen before creating any private artifacts.
    if file_sha256(source) != source_hash or file_sha256(controls) != controls_hash:
        raise ValueError('source or controls changed during preparation')
    if regional != (hk_pack_metadata(hk_regional_db) if hk_regional_db is not None else None):
        raise ValueError('regional pack changed during preparation')
    workspace.mkdir(parents=True, exist_ok=False)
    _private_directory(workspace)
    (workspace / '.gitignore').write_text('*\n', encoding='utf-8')
    oracle = {'schema_version': 1, 'rules_version': COUNTRY_RULES_VERSION,
              'repeats': repeats, 'original_records': original_records,
              'control_rows_per_block': control_rows, 'address_columns': list(address_columns),
              'original_input_sha256': source_hash, 'baseline_hashes': baseline_hashes,
              'controls_sha256': controls_hash, 'pack_sha256': file_sha256(pack),
              'hk_regional': regional, 'block': block}
    atomic_json(workspace / 'oracle.json', oracle)
    with (workspace / 'dataset.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow([*block[0]['fields'], CYCLE, BASE_ROW])
        for cycle in range(1, repeats + 1):
            for position, entry in enumerate(block, 1):
                writer.writerow([*entry['fields'].values(), cycle, position])
    if source_hash != file_sha256(source) or any(
            file_sha256(baseline / name) != value for name, value in baseline_hashes.items()):
        raise ValueError('source or completed baseline changed during preparation')
    keys = set()
    for position, entry in enumerate(block, 1):
        rec = _record(position, source, entry['fields'], address_columns)
        keys.add((rec.address_text, rec.country_hint))
    info = {key: value for key, value in oracle.items() if key not in {'block', 'baseline_hashes'}}
    info.update(block_records=len(block), total_records=len(block) * repeats,
                oracle_sha256=file_sha256(workspace / 'oracle.json'),
                public_control_addresses=len(pool), distinct_classification_keys=len(keys),
                repetition_pattern='whole-block', source_bytes=(workspace / 'dataset.csv').stat().st_size,
                dataset_sha256=file_sha256(workspace / 'dataset.csv'))
    atomic_json(workspace / 'workload.json', info)
    return info


def _safe_name(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,60}', name):
        raise ValueError('invalid benchmark run name')
    return name


def _load_workload(workspace):
    info = json.loads((workspace / 'workload.json').read_text(encoding='utf-8'))
    if file_sha256(workspace / 'oracle.json') != info.get('oracle_sha256'):
        raise ValueError('benchmark oracle hash changed')
    oracle = json.loads((workspace / 'oracle.json').read_text(encoding='utf-8'))
    for key in ('schema_version', 'rules_version', 'repeats', 'original_records',
                'control_rows_per_block', 'address_columns', 'original_input_sha256',
                'controls_sha256', 'pack_sha256', 'hk_regional'):
        if info.get(key) != oracle.get(key):
            raise ValueError('benchmark oracle metadata changed')
    if (info['block_records'] != len(oracle['block']) or
            info['total_records'] != len(oracle['block']) * oracle['repeats'] or
            info['original_records'] + info['control_rows_per_block'] != len(oracle['block'])):
        raise ValueError('benchmark oracle counts changed')
    return info, oracle


def _revision():
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                            check=True, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'diff', '--quiet', 'HEAD'], cwd=ROOT, capture_output=True)
    if dirty.returncode not in (0, 1):
        raise ValueError('cannot verify benchmark code state')
    # A dirty boolean alone cannot distinguish two different dirty versions;
    # include tracked and untracked runtime sources actually used by this tool.
    paths = [*ROOT.joinpath('src').rglob('*.py'),
             *ROOT.joinpath('src', 'world_address_engine', 'resources').glob('*.json')]
    paths += [path for name in ('benchmark_country_repeat.py', 'country_benchmark_verify.py',
                               'benchmark_batch.py') if (path := ROOT / 'tools' / name).is_file()]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode('utf-8') + b'\0')
        digest.update(bytes.fromhex(file_sha256(path)))
    return {'commit': result.stdout.strip(), 'tracked_tree_dirty': bool(dirty.returncode),
            'runtime_source_sha256': digest.hexdigest()}


def run_workload(workspace, pack, name='uninterrupted', *, resume=False, stop_after=None, batch_size=1000,
                 hk_regional_db=None):
    """Called as a separate OS process for each uninterrupted/stop/resume leg."""
    from benchmark_batch import peak_rss_bytes, tree_size
    workspace, pack = Path(workspace).resolve(), Path(pack).resolve()
    name = _safe_name(name)
    info, _oracle = _load_workload(workspace)
    identity = _revision()
    if file_sha256(workspace / 'dataset.csv') != info['dataset_sha256']:
        raise ValueError('benchmark dataset hash changed')
    if file_sha256(pack) != info['pack_sha256']:
        raise ValueError('benchmark database hash changed')
    if info['rules_version'] != COUNTRY_RULES_VERSION:
        raise ValueError('benchmark rules changed')
    regional = hk_pack_metadata(hk_regional_db) if hk_regional_db is not None else None
    if info.get('hk_regional') != regional:
        raise ValueError('benchmark regional selection changed')
    output = workspace / name
    started, last_written = time.perf_counter(), 0.0
    cancel = False
    peak_checkpoint = 0
    stages = {}
    classify_calls = 0
    inference_calls = 0
    original_classify, original_infer = CountryClassifier.classify, CountryClassifier._infer

    def counted_classify(classifier, record):
        nonlocal classify_calls
        classify_calls += 1
        return original_classify(classifier, record)

    def counted_infer(classifier, text, hint):
        nonlocal inference_calls
        inference_calls += 1
        return original_infer(classifier, text, hint)
    progress_file = workspace / f'progress-{name}.json'

    def committed(count):
        nonlocal cancel
        if stop_after is not None and count >= stop_after:
            cancel = True

    def event(payload):
        nonlocal last_written, peak_checkpoint
        elapsed = time.perf_counter() - started
        stage = payload['stage']
        new_stage = stage not in stages
        if new_stage:
            stages[stage] = round(elapsed, 3)
            peak_checkpoint = max(peak_checkpoint, tree_size(output / '.country-state'))
        if elapsed - last_written >= 1 or new_stage:
            snapshot = {**payload, 'elapsed_seconds': round(elapsed, 3),
                        'target_records': info['total_records'], 'resume': resume,
                        'peak_rss_bytes': peak_rss_bytes(), 'classify_calls': classify_calls,
                        'inference_calls': inference_calls, 'process_id': os.getpid(), **identity}
            atomic_json(progress_file, snapshot)
            last_written = elapsed

    CountryClassifier.classify, CountryClassifier._infer = counted_classify, counted_infer
    try:
        if resume:
            result = resume_analysis(output, on_progress=committed, on_event=event,
                                     cancel_requested=lambda: cancel)
        else:
            result = analyze_job(workspace / 'dataset.csv', output, pack,
                                 {'address_columns': info['address_columns']}, batch_size=batch_size,
                                 hk_regional_db=hk_regional_db,
                                 on_progress=committed, on_event=event, cancel_requested=lambda: cancel)
    finally:
        CountryClassifier.classify, CountryClassifier._infer = original_classify, original_infer
    if _revision() != identity:
        raise ValueError('benchmark code changed during measurement')
    seconds = time.perf_counter() - started
    peak_checkpoint = max(peak_checkpoint, tree_size(output / '.country-state'))
    metrics = {'run_status': result['run_status'], 'resume': resume,
               'process_id': os.getpid(), 'classify_calls': classify_calls,
               'inference_calls': inference_calls, **identity,
               'seconds': round(seconds, 3), 'peak_rss_bytes': peak_rss_bytes(),
               'checkpoint_bytes': peak_checkpoint, 'stage_started_seconds': stages,
               'source_bytes': info['source_bytes'], 'target_records': info['total_records'],
               'record_count': result.get('total_records', result.get('committed_records')),
               'status_counts': result.get('status_counts'), 'destination_counts': result.get('destination_counts'),
               'records_per_second': round(info['total_records'] / seconds, 2) if result['run_status'] == 'COMPLETE' and not resume else None,
               'completed_report_bytes': sum(p.stat().st_size for p in output.iterdir() if p.is_file()),
               'checkpoint_removed': not (output / '.country-state').exists(),
               'rules_version': COUNTRY_RULES_VERSION, 'hk_regional': regional}
    atomic_json(workspace / f'metrics-{name}-{"resume" if resume else "start"}.json', metrics)
    return metrics


def verify_workload(workspace, name='uninterrupted', compare=None):
    from country_benchmark_verify import verify_repeated_output
    from benchmark_batch import peak_rss_bytes
    workspace = Path(workspace).resolve()
    name = _safe_name(name)
    info, oracle = _load_workload(workspace)
    if file_sha256(workspace / 'dataset.csv') != info['dataset_sha256']:
        raise ValueError('benchmark dataset hash changed')
    started = time.perf_counter()
    result = verify_repeated_output(workspace / 'dataset.csv', workspace / name,
                                    oracle['block'], oracle['repeats'])
    if compare:
        other = workspace / _safe_name(compare)
        reports = ('Classified_Addresses.csv', 'Country_Diagnostics.csv', 'Country_Summary.csv')
        result['byte_identical_to_uninterrupted'] = all(
            file_sha256(workspace / name / file) == file_sha256(other / file) for file in reports)
        if not result['byte_identical_to_uninterrupted']:
            raise ValueError('recovery reports differ from uninterrupted reports')
    result.update(verification_seconds=round(time.perf_counter() - started, 3),
                  verification_peak_rss_bytes=peak_rss_bytes())
    atomic_json(workspace / f'verification-{name}.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    prep = sub.add_parser('prepare')
    for name in ('source', 'baseline', 'controls', 'workspace', 'pack'):
        prep.add_argument('--' + name, type=Path, required=True)
    prep.add_argument('--repeats', type=int, default=100)
    prep.add_argument('--control-rows', type=int, default=396)
    prep.add_argument('--hk-regional-db', type=Path)
    for op in ('run', 'resume'):
        command = sub.add_parser(op)
        command.add_argument('--workspace', type=Path, required=True)
        command.add_argument('--pack', type=Path, required=True)
        command.add_argument('--name', default='uninterrupted')
        command.add_argument('--stop-after', type=int)
        command.add_argument('--batch-size', type=int, default=1000)
        command.add_argument('--hk-regional-db', type=Path)
    verification = sub.add_parser('verify')
    verification.add_argument('--workspace', type=Path, required=True)
    verification.add_argument('--name', default='uninterrupted')
    verification.add_argument('--compare')
    args = vars(parser.parse_args())
    op = args.pop('operation')
    if op == 'prepare':
        result = prepare_workload(**args)
    elif op == 'verify':
        result = verify_workload(**args)
    else:
        result = run_workload(**args, resume=op == 'resume')
    print(json.dumps(result, ensure_ascii=True, indent=2), flush=True)


if __name__ == '__main__':
    main()
