"""Streaming, read-only case views of completed country report pairs."""
from contextlib import closing
import csv
import hashlib
import io
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from world_address_engine.io.country_reports import _private_directory
from world_address_engine.io.reports import _protect

PAGE_SIZE = 100
MODES = ('pending', 'inferred', 'all')
EXPORT_HEADER = ('Source_Record_No', 'Address', 'Status', 'Country_Code', 'Reason', 'Candidates')
REASONS = {
    'HK_REGIONAL_ADDRESS_MATCH': 'Supporting address details match the offline Hong Kong address pack.',
    'EMPTY_ADDRESS': 'No address text was supplied.',
    'UNDECODABLE_TEXT': 'Some input text could not be decoded with the selected encoding.',
    'FORMULA_WITHOUT_CACHED_VALUE': 'An address formula has no saved value. Recalculate and save the workbook.',
    'ADDRESS_TOO_LONG': 'The address exceeds the supported length.',
    'NO_ADDRESS_CONTEXT': 'Not enough address context to choose a country.',
    'NO_GEOGRAPHIC_MATCH': 'No usable country or locality was found.',
    'CONFLICTING_COUNTRIES': 'The address contains conflicting explicit countries.',
    'CONFLICTING_ADMINISTRATIVE_REGIONS': 'The address contains conflicting administrative regions.',
    'MULTIPLE_PLAUSIBLE_COUNTRIES': 'More than one country remains plausible.',
    'GEOGRAPHIC_OCCURRENCE_LIMIT': 'Too many locality matches to choose safely.',
}

# TXT readers can legitimately produce an ADDRESS_TOO_LONG report field larger
# than csv's default 128 KiB. Raise once; restoring a process-global limit would
# race other CSV readers on worker threads. Pages still retain at most 100 rows.
csv.field_size_limit(sys.maxsize)


class _DigestReader(io.RawIOBase):
    """Hash the exact bytes parsed, not a different preliminary file snapshot."""

    def __init__(self, path):
        super().__init__()
        self.source = None
        self.source = path.open('rb')
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.source.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
        return count

    def close(self):
        if self.source is not None:
            self.source.close()
        super().close()


class CaseReadCancelled(Exception):
    """No partial page or case export should be presented as complete."""


def _check_cancel(cancel_requested):
    if cancel_requested is not None and cancel_requested():
        raise CaseReadCancelled('Case operation cancelled; completed reports were not changed.')


def _manifest(output):
    manifest = json.loads((output / 'Run_Manifest.json').read_text(encoding='utf-8-sig'))
    total = manifest.get('total_records')
    if (manifest.get('job_kind') != 'country-analysis'
            or manifest.get('run_status', manifest.get('state')) != 'COMPLETE'
            or type(total) is not int or total < 0):
        raise ValueError('Case review requires a completed country-analysis manifest.')
    return manifest


def _paired_cases(output, *, address_columns=(), cancel_requested=None):
    """Pair by position, never DictReader (original Country_Code may be repeated)."""
    _check_cancel(cancel_requested)
    manifest = _manifest(output)
    names = ('Classified_Addresses.csv', 'Country_Diagnostics.csv')
    checksums = manifest.get('sha256', {})
    if any(not re.fullmatch('[0-9a-f]{64}', str(checksums.get(name, ''))) for name in names):
        raise ValueError('Case reports require manifest checksums.')
    columns = address_columns or manifest.get('run_metadata', {}).get('address_columns', ())
    with _DigestReader(output / names[0]) as detail_bytes, _DigestReader(output / names[1]) as diagnostic_bytes, \
            io.TextIOWrapper(detail_bytes, encoding='utf-8-sig', newline='') as detail, \
            io.TextIOWrapper(diagnostic_bytes, encoding='utf-8-sig', newline='') as diagnostics:
        source, diagnoses = csv.reader(detail, strict=True), csv.reader(diagnostics, strict=True)
        header, diagnostic_header = next(source, []), next(diagnoses, [])
        if not header or header[-1] != 'Country_Code' or diagnostic_header != [
                'Source_Record_No', 'Status', 'Reason', 'Candidates']:
            raise ValueError('Country case report headers are invalid.')
        selected_names = {_protect(column) for column in columns}
        indices = [i for i, name in enumerate(header[:-1]) if not columns or name in selected_names]
        if columns and any(_protect(column) not in header[:-1] for column in columns):
            raise ValueError('Saved address columns are not present in the case report.')
        if columns and any(header[:-1].count(name) > 1 for name in selected_names):
            raise ValueError('Ambiguous address headers after formula protection; use unambiguous source headers.')
        previous = 0
        try:
            for number, pair in enumerate(zip_longest(source, diagnoses), 1):
                _check_cancel(cancel_requested)
                fields, diagnosis = pair
                if (fields is None or diagnosis is None or len(fields) != len(header)
                        or len(diagnosis) != 4 or diagnosis[0] != str(number)):
                    raise ValueError('Country case reports do not align by source record number.')
                _, status, reason, candidates = diagnosis
                code = fields[-1]
                if (status not in ('DETERMINED', 'INFERRED', 'UNRESOLVED')
                        or ((status == 'UNRESOLVED') != (code == ''))):
                    raise ValueError('Country case status and country code do not agree.')
                previous = number
                yield {'record_no': number, 'address': '\n'.join(fields[i] for i in indices if fields[i]),
                       'status': status, 'code': code, 'reason': reason, 'candidates': candidates,
                       'explanation': REASONS.get(reason, reason.replace('_', ' ').capitalize())}
        except csv.Error as exc:
            raise ValueError('Country case report CSV is malformed.') from exc
        if previous != manifest['total_records']:
            raise ValueError('Country case record count does not match the manifest.')
        if any(raw.digest.hexdigest() != checksums[name]
               for name, raw in zip(names, (detail_bytes, diagnostic_bytes))):
            raise ValueError('Country case report checksum mismatch; reports were changed.')


def _selected(row, mode):
    return mode == 'all' or row['status'] == ('UNRESOLVED' if mode == 'pending' else 'INFERRED')


def load_case_page(output_dir, mode='pending', after_record=0, limit=PAGE_SIZE, *,
                   address_columns=(), cancel_requested=None):
    """Return at most 100 matches plus a forward cursor; scanning stays off the UI."""
    if (mode not in MODES or type(limit) is not int or not 1 <= limit <= PAGE_SIZE
            or type(after_record) is not int or after_record < 0):
        raise ValueError('Invalid country case page options.')
    rows, has_next = [], False
    with closing(_paired_cases(Path(output_dir), address_columns=address_columns,
                               cancel_requested=cancel_requested)) as cases:
        for row in cases:
            if row['record_no'] <= after_record or not _selected(row, mode):
                continue
            if len(rows) == limit:
                has_next = True
            else:
                rows.append(row)
        # Consume to EOF to authenticate both report streams before showing rows.
    return {'rows': rows, 'has_next': has_next,
            'next_cursor': rows[-1]['record_no'] if rows else after_record}


def export_cases(output_dir, destination, mode='pending', *, address_columns=(), cancel_requested=None):
    """Export all matching cases; publish atomically and never replace any file."""
    if mode not in MODES:
        raise ValueError('Invalid country case filter.')
    output, destination = Path(output_dir).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Case export destination already exists; choose a new file.')
    if destination.is_relative_to(output):
        raise ValueError('Save case exports outside the immutable completed report folder.')
    _check_cancel(cancel_requested)
    with tempfile.TemporaryDirectory(prefix='.wase-cases-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        _private_directory(stage)
        target = stage / 'cases.csv'
        count = 0
        with target.open('w', encoding='utf-8-sig', newline='') as stream, \
                closing(_paired_cases(output, address_columns=address_columns,
                                      cancel_requested=cancel_requested)) as cases:
            writer = csv.writer(stream)
            writer.writerow(EXPORT_HEADER)
            for row in cases:
                if _selected(row, mode):
                    writer.writerow([row['record_no'], *[_protect(row[key]) for key in
                                     ('address', 'status', 'code', 'reason', 'candidates')]])
                    count += 1
            stream.flush()
            os.fsync(stream.fileno())
        target.chmod(0o600)
        _check_cancel(cancel_requested)
        # Windows rename is exclusive; POSIX rename would overwrite an existing file.
        if os.name == 'nt':
            os.rename(target, destination)
        else:
            os.link(target, destination)
    return count
