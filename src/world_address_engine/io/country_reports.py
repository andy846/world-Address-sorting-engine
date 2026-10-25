"""Streaming country estimates. A manifest is the final completion marker."""
from collections import Counter
import csv
from functools import lru_cache
from itertools import chain
import os
from pathlib import Path
import subprocess
import tempfile

from world_address_engine.io.reports import (
    _hash, _protect, _remove_staging, _write_manifest_atomic,
)

STATUSES = ('DETERMINED', 'INFERRED', 'UNRESOLVED')
REPORT_NAMES = ('Classified_Addresses.csv', 'Country_Summary.csv',
                'Country_Diagnostics.csv')


@lru_cache(maxsize=1)
def _user_sid() -> str:
    result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                            capture_output=True, check=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    sid = next(csv.reader([result.stdout.decode(errors='replace').strip()]))[1]
    if not sid.startswith('S-1-'):
        raise OSError('cannot identify checkpoint owner')
    return sid


def _private_directory(path: Path) -> None:
    """Protect sensitive files before writing, including on Windows NTFS."""
    if os.name == 'nt':
        result = subprocess.run(
            ['icacls', str(path), '/inheritance:r', '/grant:r',
             f'*{_user_sid()}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
            capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise OSError('cannot restrict country analysis directory permissions')
    else:
        path.chmod(0o700)


def write_country_reports(items, output_dir: Path, catalogue, run_metadata: dict, *,
                          original_columns=(), allow_sparse_columns=False,
                          before_manifest=None) -> dict:
    """Write originals plus one code; percentages use all input rows as denominator.

    Unresolved records have a blank code summary row. Diagnostics deliberately
    omit original fields and inference evidence. The return value is the manifest.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / 'Run_Manifest.json').exists():
        raise FileExistsError('existing completed analysis cannot be overwritten')
    stage = Path(tempfile.mkdtemp(prefix='.country-report-', dir=output_dir))
    statuses = Counter(dict.fromkeys(STATUSES, 0))
    destinations = Counter()
    previous = 0
    try:
        _private_directory(stage)
        iterator = iter(items)
        first = next(iterator, None)
        columns = list(original_columns) or (list(first[0].fields) if first else [])
        with (stage / REPORT_NAMES[0]).open('w', encoding='utf-8-sig', newline='') as detail, \
                (stage / REPORT_NAMES[2]).open('w', encoding='utf-8-sig', newline='') as diagnostic:
            # Positional writers also preserve an original Country_Code column.
            writer = csv.writer(detail)
            writer.writerow([_protect(column) for column in columns] + ['Country_Code'])
            diagnoses = csv.writer(diagnostic)
            diagnoses.writerow(['Source_Record_No', 'Status', 'Reason', 'Candidates'])
            for record, inference in chain((first,) if first else (), iterator):
                if record.record_no != previous + 1 or inference.record_no != record.record_no:
                    raise ValueError('country records must be contiguous and match results')
                keys = list(record.fields)
                if keys != (columns[:len(keys)] if allow_sparse_columns else columns):
                    raise ValueError('source schema changed inside country analysis')
                code, status = inference.country_code, inference.status
                if status not in STATUSES or ((code is None) != (status == 'UNRESOLVED')):
                    raise ValueError('invalid country inference status or code')
                if code is not None and code not in catalogue.entries:
                    raise ValueError('country inference code is outside the catalogue')
                if any(candidate not in catalogue.entries for candidate in inference.candidates):
                    raise ValueError('country inference candidate is outside the catalogue')
                previous = record.record_no
                statuses[status] += 1
                if code is not None:
                    destinations[code] += 1
                writer.writerow([_protect(record.fields.get(key, '')) for key in columns] + [code or ''])
                diagnoses.writerow([record.record_no, status, _protect(inference.reason),
                                    _protect(';'.join(inference.candidates))])
        if sum(destinations.values()) + statuses['UNRESOLVED'] != previous:
            raise ValueError('country statistics reconciliation failed')
        with (stage / REPORT_NAMES[1]).open('w', encoding='utf-8-sig', newline='') as summary:
            writer = csv.writer(summary)
            writer.writerow(['Country_Code', 'Country_Name_TC', 'Country_Name_EN',
                             'Count', 'Percentage'])
            for code, count in sorted(destinations.items()):
                entry = catalogue.entries[code]
                writer.writerow([_protect(code), _protect(entry.name_tc), _protect(entry.name_en),
                                 count, f'{count * 100 / previous:.2f}'])
            if statuses['UNRESOLVED']:
                count = statuses['UNRESOLVED']
                writer.writerow(['', '', '', count, f'{count * 100 / previous:.2f}'])
        for name in REPORT_NAMES:
            (stage / name).chmod(0o600)
        checksums = {name: _hash(stage / name) for name in REPORT_NAMES}
        manifest = {
            'run_status': 'COMPLETE', 'job_kind': 'country-analysis',
            'data_class': 'COUNTRY_CODE_ESTIMATE', 'total_records': previous,
            'status_counts': dict(statuses), 'destination_counts': dict(sorted(destinations.items())),
            'run_metadata': dict(run_metadata), 'files': list(REPORT_NAMES), 'sha256': checksums,
        }
        if (output_dir / 'Run_Manifest.json').exists():
            raise FileExistsError('existing completed analysis cannot be overwritten')
        for name in REPORT_NAMES:
            os.replace(stage / name, output_dir / name)
        _remove_staging(stage)
        if before_manifest is not None:
            before_manifest()
        _write_manifest_atomic(output_dir, manifest)
        return manifest
    finally:
        _remove_staging(stage)
