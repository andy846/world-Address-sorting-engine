"""Read-only, bounded-memory verification of repeated country-analysis jobs.

The oracle is supplied independently of exported Country_Code fields. Neither
success metrics nor failure messages contain source cells, paths or row details.
"""
from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
import io
from itertools import zip_longest
import json
from pathlib import Path
import re

from world_address_engine.io.country_reports import REPORT_NAMES, STATUSES
from world_address_engine.io.reports import _protect

METADATA_COLUMNS = ('_Benchmark_Cycle', '_Benchmark_Base_Row')
DIAGNOSTIC_COLUMNS = ['Source_Record_No', 'Status', 'Reason', 'Candidates']
SUMMARY_COLUMNS = ['Country_Code', 'Country_Name_TC', 'Country_Name_EN', 'Count', 'Percentage']
GENERATED_COLUMNS = ['Country_Code', 'Zone_Code', 'NOVSN_Zone_Code']
SUMMARY_COLUMNS_V2 = SUMMARY_COLUMNS[:3] + GENERATED_COLUMNS[1:] + SUMMARY_COLUMNS[3:]


def report_contract(manifest):
    """Missing version is the historical schema 1, never a schema 2 fallback."""
    version = manifest.get('report_schema_version', 1)
    _require(type(version) is int and version in (1, 2))
    generated = GENERATED_COLUMNS if version == 2 else ['Country_Code']
    if version == 2 or 'generated_columns' in manifest:
        _require(manifest.get('generated_columns') == generated)
    metadata = manifest.get('run_metadata', {})
    if version == 2:
        valid_zone_identity(metadata.get('zone_mapping'))
    else:
        _require('zone_mapping' not in metadata)
    return version, generated


def valid_zone_identity(identity):
    _require(isinstance(identity, dict) and set(identity) == {'version', 'source_sha256', 'sha256'})
    _require(isinstance(identity['version'], str) and bool(identity['version'].strip()))
    _require(all(isinstance(identity[key], str) and re.fullmatch('[0-9a-f]{64}', identity[key])
                 for key in ('source_sha256', 'sha256')))


class _HashedReader(io.RawIOBase):
    """Authenticate the same bytes the CSV parser consumes, in bounded buffers."""

    def __init__(self, raw):
        super().__init__()
        self.raw = raw
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.raw.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
        return count


def _csv_input(stack, path):
    raw = stack.enter_context(path.open('rb', buffering=0))
    hashed = _HashedReader(raw)
    text = stack.enter_context(io.TextIOWrapper(io.BufferedReader(hashed),
                                               encoding='utf-8-sig', newline=''))
    return csv.reader(text, strict=True), hashed.digest


def _require(condition):
    if not condition:
        raise ValueError('benchmark verification failed')


def _exact_counts(actual, expected):
    return (isinstance(actual, dict) and actual == expected
            and all(type(value) is int for value in actual.values()))


def _verify(source, output, block, repeats, zone_mapping=None, run_metadata=None,
            report_schema_version=None):
    _require(type(repeats) is int and repeats > 0)
    _require(isinstance(block, list) and bool(block))
    _require(isinstance(block[0], dict) and isinstance(block[0].get('fields'), dict))
    columns = list(block[0]['fields'])
    _require(bool(columns) and all(isinstance(key, str) and key for key in columns))
    _require(not set(columns).intersection(METADATA_COLUMNS))
    with (output / 'Run_Manifest.json').open(encoding='utf-8-sig') as stream:
        manifest = json.load(stream)
    _require(isinstance(manifest, dict))
    version, generated = report_contract(manifest)
    metadata = manifest.get('run_metadata')
    _require(isinstance(metadata, dict))
    if report_schema_version is not None:
        _require(type(report_schema_version) is int and version == report_schema_version)
    if zone_mapping is not None:
        valid_zone_identity(zone_mapping)
        _require(version == 2 and metadata.get('zone_mapping') == zone_mapping)
    if run_metadata is not None:
        _require(isinstance(run_metadata, dict))
        _require(all(key in metadata and metadata[key] == value for key, value in run_metadata.items()))
    destinations, statuses = Counter(), Counter(dict.fromkeys(STATUSES, 0))
    zone_pairs = {}
    max_field = 0
    for item in block:
        _require(isinstance(item, dict))
        fields = item.get('fields')
        _require(isinstance(fields, dict) and list(fields) == columns)
        _require(all(isinstance(value, str) for value in fields.values()))
        code, status = item.get('code'), item.get('status')
        _require(status in STATUSES)
        _require((code is None) == (status == 'UNRESOLVED'))
        _require(code is None or (isinstance(code, str) and re.fullmatch('[A-Z]{2}', code)))
        if version == 2:
            pair = (item.get('zone_code'), item.get('novsn_zone_code'))
            _require(all(isinstance(value, str) for value in pair))
            _require(all(pair) if code else pair == ('', ''))
            _require(code not in zone_pairs or zone_pairs[code] == pair)
            zone_pairs[code] = pair
            max_field = max(max_field, *(len(value) + 1 for value in pair))
        else:
            _require('zone_code' not in item and 'novsn_zone_code' not in item)
        candidates = item.get('candidates')
        _require(isinstance(item.get('reason'), str) and isinstance(candidates, list))
        _require(all(isinstance(code, str) and re.fullmatch('[A-Z]{2}', code)
                     for code in candidates))
        statuses[status] += repeats
        if code is not None:
            destinations[code] += repeats
        max_field = max(max_field, *(len(value) + 1 for value in fields.values()),
                        len(item['reason']) + 1, len(';'.join(candidates)) + 1)
    max_field = max(max_field, *(len(key) + 1 for key in columns))
    total = len(block) * repeats
    countries = dict(destinations)
    if statuses['UNRESOLVED']:
        countries[''] = statuses['UNRESOLVED']
    _require(manifest.get('run_status') == 'COMPLETE'
             and manifest.get('job_kind') == 'country-analysis'
             and manifest.get('data_class') == 'COUNTRY_CODE_ESTIMATE')
    _require(type(manifest.get('total_records')) is int and manifest['total_records'] == total)
    _require(_exact_counts(manifest.get('status_counts'), dict(statuses)))
    _require(_exact_counts(manifest.get('destination_counts'), dict(destinations)))
    _require(manifest.get('files') == list(REPORT_NAMES))
    hashes = manifest.get('sha256')
    _require(isinstance(hashes, dict) and set(hashes) == set(REPORT_NAMES))
    _require(all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)
                 for value in hashes.values()))

    old_limit = csv.field_size_limit()
    # Bound by the oracle, not the full workload. Restore the process setting.
    csv.field_size_limit(max(old_limit, max_field))
    try:
        with ExitStack() as stack:
            raw, source_digest = _csv_input(stack, source)
            detail, detail_digest = _csv_input(stack, output / REPORT_NAMES[0])
            diagnostic, diagnostic_digest = _csv_input(stack, output / REPORT_NAMES[2])
            source_columns = columns + list(METADATA_COLUMNS)
            _require(next(raw, None) == source_columns)
            _require(next(detail, None) == [_protect(key) for key in source_columns] + generated)
            _require(next(diagnostic, None) == DIAGNOSTIC_COLUMNS)
            observed = 0
            for number, (original, exported, diagnosis) in enumerate(
                    zip_longest(raw, detail, diagnostic), 1):
                _require(number <= total and original is not None
                         and exported is not None and diagnosis is not None)
                cycle, position = divmod(number - 1, len(block))
                expected = block[position]
                cells = list(expected['fields'].values()) + [str(cycle + 1), str(position + 1)]
                _require(original == cells)
                tail = [expected['code'] or '']
                if version == 2:
                    tail.extend(zone_pairs[expected['code']])
                _require(exported == [_protect(value) for value in cells + tail])
                _require(diagnosis == [str(number), expected['status'], _protect(expected['reason']),
                                       _protect(';'.join(expected['candidates']))])
                observed = number
            _require(observed == total)
            _require(source_digest.hexdigest() == metadata.get('input_sha256'))
            _require(detail_digest.hexdigest() == hashes[REPORT_NAMES[0]])
            _require(diagnostic_digest.hexdigest() == hashes[REPORT_NAMES[2]])
            summary, summary_digest = _csv_input(stack, output / REPORT_NAMES[1])
            summary_columns = SUMMARY_COLUMNS_V2 if version == 2 else SUMMARY_COLUMNS
            _require(next(summary, None) == summary_columns)
            seen = set()
            for row in summary:
                _require(len(row) == len(summary_columns))
                code, name_tc, name_en = row[:3]
                count, percent = row[-2:]
                _require(code in countries and code not in seen)
                if version == 2:
                    _require(row[3:5] == [_protect(value) for value in zone_pairs[code or None]])
                _require(count == str(countries[code]))
                _require(percent == f'{countries[code] * 100 / total:.2f}')
                _require(bool(code) or (name_tc == '' and name_en == ''))
                seen.add(code)
            _require(seen == set(countries))
            _require(summary_digest.hexdigest() == hashes[REPORT_NAMES[1]])
    finally:
        csv.field_size_limit(old_limit)
    return {'verified': True, 'total_records': total, 'block_records': len(block),
            'repeats': repeats, 'destination_counts': dict(sorted(destinations.items())),
            'country_counts': dict(sorted(countries.items())), 'status_counts': dict(statuses),
            'source_sha256': source_digest.hexdigest(), 'sha256': dict(hashes)}


def verify_repeated_output(source: Path, output: Path, block: list[dict], repeats: int, *,
                           zone_mapping=None, run_metadata=None, report_schema_version=None) -> dict:
    """Verify a repeated-block CSV and all completed reports without mutation.

    ``block`` contains exact source fields and independent code/status/reason/
    candidates for each base record. Source Country_Code values are preserved
    as ordinary fields; only the supplied oracle determines expected results.
    Memory scales with the base block and individual CSV rows, never repeats.
    Raises ValueError with a value-free message on any validation/read failure.
    """
    try:
        return _verify(Path(source), Path(output), block, repeats, zone_mapping,
                       run_metadata, report_schema_version)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, csv.Error):
        raise ValueError('benchmark verification failed') from None
