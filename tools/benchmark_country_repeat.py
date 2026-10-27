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
from country_benchmark_verify import (GENERATED_COLUMNS, DIAGNOSTIC_COLUMNS,
                                      SUMMARY_COLUMNS, SUMMARY_COLUMNS_V2,
                                      report_contract, valid_zone_identity)

CYCLE = '_Benchmark_Cycle'
BASE_ROW = '_Benchmark_Base_Row'
FORBIDDEN = {CYCLE, BASE_ROW, 'Country_Code', 'Country', 'COUNTRY'}


def _read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        yield from csv.reader(stream, strict=True)


def _zone_identity(zones):
    result = {'version': zones.version, 'source_sha256': zones.source_sha256,
              'sha256': zones.fingerprint}
    valid_zone_identity(result)
    return result


def _oracle_item(fields, found, zones):
    from world_address_engine.data.zone_mappings import zone_values
    zone, novsn = zone_values(found.country_code, zones)
    return {'fields': fields, 'code': found.country_code, 'status': found.status,
            'reason': found.reason, 'candidates': list(found.candidates),
            'zone_code': zone, 'novsn_zone_code': novsn}


def _baseline_block(source, baseline, pack, hk_regional=None, zones=None):
    from world_address_engine.data.zone_mappings import load_zone_mappings, zone_values
    zones = zones if zones is not None else load_zone_mappings()
    manifest = json.loads((baseline / 'Run_Manifest.json').read_text(encoding='utf-8-sig'))
    metadata = manifest.get('run_metadata', {})
    version, generated = report_contract(manifest)
    if version == 2 and metadata.get('zone_mapping') != _zone_identity(zones):
        raise ValueError('baseline zone mapping changed')
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
    catalogue = load_country_codes()
    for key, value in _catalogue_metadata(catalogue).items():
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
    detail = _read(baseline / 'Classified_Addresses.csv')
    detail_columns = next(detail, None)
    diagnostic = _read(baseline / 'Country_Diagnostics.csv')
    if next(diagnostic, None) != DIAGNOSTIC_COLUMNS:
        raise ValueError('baseline diagnostic columns changed')
    statuses = Counter(dict.fromkeys(('DETERMINED', 'INFERRED', 'UNRESOLVED'), 0))
    counts = Counter()
    for original, exported, diag in zip_longest(
            records, detail, diagnostic):
        if original is None or exported is None or diag is None:
            raise ValueError('baseline/source row count mismatch')
        if FORBIDDEN.intersection(original.fields):
            raise ValueError('benchmark source has a reserved metadata or trusted-hint column')
        if (detail_columns != [_protect(key) for key in original.fields] + generated or
                len(exported) != len(original.fields) + len(generated)):
            raise ValueError('baseline original columns changed')
        if exported[:len(original.fields)] != [_protect(value) for value in original.fields.values()]:
            raise ValueError('baseline original field mismatch')
        if len(diag) != 4 or diag[0] != str(original.record_no):
            raise ValueError('baseline record order mismatch')
        code = exported[len(original.fields)] or None
        if ((code is not None and code not in catalogue.entries) or
                diag[1] not in statuses or ((code is None) != (diag[1] == 'UNRESOLVED'))):
            raise ValueError('baseline country/status changed')
        candidates = diag[3].split(';') if diag[3] else []
        if any(candidate not in catalogue.entries for candidate in candidates):
            raise ValueError('baseline candidates changed')
        zone, novsn = zone_values(code, zones)
        if version == 2 and exported[-2:] != [_protect(zone), _protect(novsn)]:
            raise ValueError('baseline zone pair changed')
        block.append({'fields': dict(original.fields), 'code': code,
                      'status': diag[1], 'reason': diag[2], 'candidates': candidates,
                      'zone_code': zone, 'novsn_zone_code': novsn})
        statuses[diag[1]] += 1
        counts[code or ''] += 1
    if not block or len(block) != manifest['total_records']:
        raise ValueError('baseline source count mismatch or empty source')
    if (manifest.get('status_counts') != dict(statuses) or
            manifest.get('destination_counts') != {code: n for code, n in counts.items() if code}):
        raise ValueError('baseline counts changed')
    summary = _read(baseline / 'Country_Summary.csv')
    summary_columns = SUMMARY_COLUMNS_V2 if version == 2 else SUMMARY_COLUMNS
    if next(summary, None) != summary_columns:
        raise ValueError('baseline summary columns changed')
    seen = set()
    for row in summary:
        if len(row) != len(summary_columns) or row[0] not in counts or row[0] in seen:
            raise ValueError('baseline summary countries changed')
        code = row[0]
        if row[-2:] != [str(counts[code]), f'{counts[code] * 100 / len(block):.2f}']:
            raise ValueError('baseline summary counts changed')
        if version == 2 and row[3:5] != [_protect(value) for value in zone_values(code, zones)]:
            raise ValueError('baseline summary zone pair changed')
        if not code and row[1:3] != ['', '']:
            raise ValueError('baseline unresolved summary names changed')
        seen.add(code)
    if seen != set(counts):
        raise ValueError('baseline summary countries missing')
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
    from world_address_engine.data.zone_mappings import load_zone_mappings
    from world_address_engine.data.country_codes import load_country_codes
    from world_address_engine.jobs.country_analysis import _catalogue_metadata
    zones = load_zone_mappings()
    zone_mapping = _zone_identity(zones)
    block, address_columns, manifest = _baseline_block(source, baseline, pack, regional, zones)
    source_hash = file_sha256(source)
    baseline_hashes = {name: file_sha256(baseline / name) for name in
                       ('Run_Manifest.json', 'Classified_Addresses.csv', 'Country_Diagnostics.csv', 'Country_Summary.csv')}
    original_records = len(block)
    controls_hash = file_sha256(controls)
    public = json.loads(controls.read_text(encoding='utf-8'))
    pool = public.get('controls', [])
    if public.get('schema_version') != 1 or not pool:
        raise ValueError('public control source manifest missing')
    if (not all(isinstance(c, dict) and isinstance(c.get('control_id'), str)
                and c['control_id'] for c in pool) or
            len({c['control_id'] for c in pool}) != len(pool)):
        raise ValueError('duplicate public control identifier')
    catalogue = load_country_codes()
    for control in pool:
        if (control.get('expected_code') not in catalogue.entries or
                not isinstance(control.get('source_url'), str) or
                not control['source_url'].startswith('https://') or
                not isinstance(control.get('lines'), list) or not control['lines'] or
                len(control['lines']) > len(address_columns) or
                not all(isinstance(line, str) for line in control['lines'])):
            raise ValueError('public control source/label/address columns are invalid')
    verified_controls = []
    with CountryClassifier(pack, hk_regional_db=hk_regional_db) as classifier:
        for control in pool:
            fields = dict.fromkeys(block[0]['fields'], '')
            for column, line in zip(address_columns, control['lines']):
                fields[column] = line
            rec = _record(1, source, fields, address_columns)
            found = classifier.classify(rec)
            if found.country_code != control['expected_code']:
                raise ValueError('public control classification disagrees with its independent label')
            verified_controls.append(_oracle_item(fields, found, zones))
    for index in range(control_rows):
        entry = verified_controls[index % len(verified_controls)]
        fields = dict(entry['fields'])
        if 'Control no' in fields:
            fields['Control no'] = f'PUBLIC-BENCHMARK-{index + 1:06d}'
        block.append({**entry, 'fields': fields})
    # All validity/control checks happen before creating any private artifacts.
    if file_sha256(source) != source_hash or file_sha256(controls) != controls_hash:
        raise ValueError('source or controls changed during preparation')
    if regional != (hk_pack_metadata(hk_regional_db) if hk_regional_db is not None else None):
        raise ValueError('regional pack changed during preparation')
    if _zone_identity(load_zone_mappings()) != zone_mapping:
        raise ValueError('zone mapping changed during preparation')
    workspace.mkdir(parents=True, exist_ok=False)
    _private_directory(workspace)
    (workspace / '.gitignore').write_text('*\n', encoding='utf-8')
    reference_metadata = {key: value for key, value in manifest['run_metadata'].items()
                          if key in ('geo_sha256', 'geo_manifest_sha256', 'geo_pack_version',
                                     'pack_format_version', 'profile')}
    oracle = {'schema_version': 2, 'report_schema_version': 2,
              'generated_columns': list(GENERATED_COLUMNS), 'zone_mapping': zone_mapping,
              'catalogue_metadata': _catalogue_metadata(catalogue),
              'reference_metadata': reference_metadata, 'rules_version': COUNTRY_RULES_VERSION,
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
    if type(info.get('schema_version')) is not int or info['schema_version'] not in (1, 2):
        raise ValueError('unsupported benchmark oracle schema')
    for key in ('schema_version', 'rules_version', 'repeats', 'original_records',
                'control_rows_per_block', 'address_columns', 'original_input_sha256',
                'controls_sha256', 'pack_sha256', 'hk_regional'):
        if info.get(key) != oracle.get(key):
            raise ValueError('benchmark oracle metadata changed')
    if info['schema_version'] == 2:
        for key in ('report_schema_version', 'generated_columns', 'zone_mapping',
                    'catalogue_metadata', 'reference_metadata'):
            if key not in info or info[key] != oracle.get(key):
                raise ValueError('benchmark oracle metadata changed')
        valid_zone_identity(info['zone_mapping'])
        if (type(info['report_schema_version']) is not int or info['report_schema_version'] != 2 or
                info['generated_columns'] != GENERATED_COLUMNS):
            raise ValueError('benchmark report schema changed')
    elif any(key in info or key in oracle for key in
             ('zone_mapping', 'report_schema_version', 'generated_columns')):
        raise ValueError('legacy benchmark identity cannot be reinterpreted')
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
    if info['schema_version'] != 2:
        raise ValueError('legacy workload is verification-only; prepare a new schema 2 workload')
    from world_address_engine.data.zone_mappings import load_zone_mappings
    from world_address_engine.data.country_codes import load_country_codes
    from world_address_engine.jobs.country_analysis import _catalogue_metadata
    if _zone_identity(load_zone_mappings()) != info['zone_mapping']:
        raise ValueError('benchmark zone mapping changed')
    if _catalogue_metadata(load_country_codes()) != info['catalogue_metadata']:
        raise ValueError('benchmark country catalogue changed')
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
    result = None
    for run in [name, *([_safe_name(compare)] if compare else [])]:
        manifest = json.loads((workspace / run / 'Run_Manifest.json').read_text(encoding='utf-8-sig'))
        if manifest.get('run_metadata', {}).get('hk_regional') != info.get('hk_regional'):
            raise ValueError('verified run regional selection differs from the pinned workload')
        metadata = {'rules_version': info['rules_version'], 'geo_sha256': info['pack_sha256']}
        options = {'report_schema_version': 1}
        if info['schema_version'] == 2:
            metadata.update(info['catalogue_metadata'])
            metadata.update(info['reference_metadata'])
            metadata['address_columns'] = info['address_columns']
            options = {'report_schema_version': 2, 'zone_mapping': info['zone_mapping']}
        checked = verify_repeated_output(workspace / 'dataset.csv', workspace / run,
                                          oracle['block'], oracle['repeats'],
                                          run_metadata=metadata, **options)
        if result is None:
            result = checked
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
