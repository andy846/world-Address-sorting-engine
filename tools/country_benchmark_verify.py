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


def _verify(source, output, block, repeats):
    _require(type(repeats) is int and repeats > 0)
    _require(isinstance(block, list) and bool(block))
    _require(isinstance(block[0], dict) and isinstance(block[0].get('fields'), dict))
    columns = list(block[0]['fields'])
    _require(bool(columns) and all(isinstance(key, str) and key for key in columns))
    _require(not set(columns).intersection(METADATA_COLUMNS))
    destinations, statuses = Counter(), Counter(dict.fromkeys(STATUSES, 0))
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
    manifest_path = output / 'Run_Manifest.json'
    with manifest_path.open(encoding='utf8') as stream:
        manifest = json.load(stream)
    _require(isinstance(manifest, dict))
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
    metadata = manifest.get('run_metadata')
    _require(isinstance(metadata, dict))

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
            _require(next(detail, None) == [_protect(key) for key in source_columns] + ['Country_Code'])
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
                _require(exported == [_protect(value) for value in cells] + [expected['code'] or ''])
                _require(diagnosis == [str(number), expected['status'], _protect(expected['reason']),
                                       _protect(';'.join(expected['candidates']))])
                observed = number
            _require(observed == total)
            _require(source_digest.hexdigest() == metadata.get('input_sha256'))
            _require(detail_digest.hexdigest() == hashes[REPORT_NAMES[0]])
            _require(diagnostic_digest.hexdigest() == hashes[REPORT_NAMES[2]])
            summary, summary_digest = _csv_input(stack, output / REPORT_NAMES[1])
            _require(next(summary, None) == SUMMARY_COLUMNS)
            seen = set()
            for row in summary:
                _require(len(row) == len(SUMMARY_COLUMNS))
                code, name_tc, name_en, count, percent = row
                _require(code in countries and code not in seen)
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


def verify_repeated_output(source: Path, output: Path, block: list[dict], repeats: int) -> dict:
    """Verify a repeated-block CSV and all completed reports without mutation.

    ``block`` contains exact source fields and independent code/status/reason/
    candidates for each base record. Source Country_Code values are preserved
    as ordinary fields; only the supplied oracle determines expected results.
    Memory scales with the base block and individual CSV rows, never repeats.
    Raises ValueError with a value-free message on any validation/read failure.
    """
    try:
        return _verify(Path(source), Path(output), block, repeats)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, csv.Error):
        raise ValueError('benchmark verification failed') from None
