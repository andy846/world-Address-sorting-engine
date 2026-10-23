"""Windows GUI entry point and offline, synthetic-fixture bundle self-test.

Windowed executables have no reliable stdout. ``--self-test --report-file PATH``
writes a JSON report and returns nonzero if any acceptance assertion fails.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
from fnmatch import fnmatchcase
from importlib.metadata import version
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

DISTRIBUTION = 'world-address-sorting-engine'
EXCLUDED_PACK_PATTERNS = ('geonames-*', '*.sqlite', '*.db', '*.sqlite.*', '*.db.*')
APPROVAL_REFUSAL = 'a signed HKP approval manifest and key are required for a production run'


def running_version() -> str:
    """Return the version of the code that is actually running.

    Installed distribution metadata can lag behind the source tree (an editable
    or stale install), so the bundle must attest to its own code version.
    """
    from world_address_engine import __version__

    return __version__


def installed_metadata_version() -> str | None:
    """Return the installed distribution version for diagnostics only."""
    try:
        return version(DISTRIBUTION)
    except Exception:
        return None


def excluded_pack_paths(names) -> list[str]:
    """Match components, including nested paths and Windows archive separators."""
    return sorted(str(name) for name in names if any(
        fnmatchcase(part.lower(), pattern)
        for part in str(name).replace('\\', '/').split('/')
        for pattern in EXCLUDED_PACK_PATTERNS))


def report_errors(report, *, expected_version: str, require_frozen: bool = False) -> list[str]:
    """Validate evidence independently of the producer's overall success flag."""
    if not isinstance(report, dict):
        return ['report must be a JSON object']
    from world_address_engine.jobs.runner import RULES_VERSION

    expected = {
        'ok': True, 'window_shown': True, 'events_processed': True,
        'classification_attempted': True, 'approval_refused': True,
        'classification_output_created': False, 'pack_bundled': False,
        'approved_codes': {}, 'review_codes': 0, 'job_state': 'idle',
        'schema_version': 1, 'version': expected_version,
        'rules_version': RULES_VERSION, 'bundled_pack_paths': [],
        'classification_error': APPROVAL_REFUSAL, 'assertion_failures': [],
    }
    if require_frozen:
        expected['frozen'] = True
    errors = [name for name, value in expected.items()
              if type(report.get(name)) is not type(value) or report[name] != value]
    if report.get('error'):
        errors.append('error')
    expected_country = {
        'window_shown': True, 'mapping_entries': 235, 'total_records': 4,
        'destination_counts': {'CN': 1, 'HK': 1, 'JP': 1}, 'unresolved': 1,
        'normalization_loaded': True,
    }
    if report.get('country_analysis') != expected_country:
        errors.append('country_analysis')
    for name, rows in (('preview', 9604), ('xlsx_preview', 1)):
        preview = report.get(name)
        shape = {'total_records': rows, 'original_columns': 12,
                 'records_with_extra_unnamed_data': 1,
                 'records_with_decoding_errors': 0, 'empty_addresses': 0,
                 'classifications_run': False,
                 'address_columns': [f'NAME_ADDRESS_LINE{i}' for i in range(1, 6)]}
        if not isinstance(preview, dict) or any(
                type(preview.get(key)) is not type(value) or preview[key] != value
                for key, value in shape.items()):
            errors.append(name)
    return errors


def self_test() -> dict:
    """Exercise the real GUI, preview readers and production approval gate."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from openpyxl import Workbook

    from world_address_engine.cli import preview
    from world_address_engine.gui.app import MainWindow
    from world_address_engine.jobs.runner import RULES_VERSION, run_job

    extraction = getattr(sys, '_MEIPASS', None)
    bundled = excluded_pack_paths(
        path.relative_to(extraction) for path in Path(extraction).rglob('*')
    ) if extraction is not None else []
    project_version = running_version()
    report = {'schema_version': 1, 'version': project_version,
              'distribution_metadata_version': installed_metadata_version(),
              'rules_version': RULES_VERSION, 'frozen': bool(getattr(sys, 'frozen', False)),
              'pack_bundled': bool(bundled), 'bundled_pack_paths': bundled,
              'classification_attempted': False, 'approval_refused': False}
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        events = []
        QTimer.singleShot(0, lambda: events.append(True))
        window.show()
        app.processEvents()
        window._load_approved_codes()
        report.update(window_shown=window.isVisible(), events_processed=bool(events),
                      job_state=window.job_state, approved_codes=window.approved_codes,
                      review_codes=window.review_code.count())
        with tempfile.TemporaryDirectory(prefix='wase-self-test-') as temporary:
            work = Path(temporary)
            source = work / 'synthetic.csv'
            headers = [f'NAME_ADDRESS_LINE{i}' for i in range(1, 6)] + ['Control no'] + [''] * 6
            first_row = ['Synthetic Recipient', '1 Example Road', 'Example District',
                         'Example City', 'Example Country', '000001', 'synthetic extra'] + [''] * 5
            with source.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(headers)
                for index in range(9604):
                    row = first_row.copy()
                    row[5] = f'{index + 1:06d}'
                    if index:
                        row[6] = ''
                    writer.writerow(row)
            report['preview'] = preview(source)
            workbook = Workbook()
            try:
                workbook.active.append(headers)
                workbook.active.append(first_row)
                workbook.save(work / 'synthetic.xlsx')
            finally:
                workbook.close()
            report['xlsx_preview'] = preview(work / 'synthetic.xlsx')

            # Satisfy the pack format probe so refusal comes from the approval
            # gate, rather than from a missing input or invalid database.
            geo_db, hkp_db = work / 'synthetic-geo.db', work / 'synthetic-hkp.db'
            with closing(sqlite3.connect(geo_db)) as conn:
                conn.execute('CREATE TABLE geo_aliases (search_key TEXT)')
            with closing(sqlite3.connect(hkp_db)) as conn:
                conn.execute('CREATE TABLE metadata (catalogue_version TEXT)')
            output = work / 'classification-output'
            report['classification_attempted'] = True
            try:
                run_job(source, output, geo_db, hkp_db, {})
            except ValueError as exc:
                report['approval_refused'] = str(exc) == APPROVAL_REFUSAL
                report['classification_error'] = str(exc)
            report['classification_output_created'] = output.exists()
            from world_address_engine.data.country_codes import load_country_codes
            from world_address_engine.gui.country_app import CountryAnalysisWindow
            from world_address_engine.jobs.country_analysis import analyze_job
            from world_address_engine.matching.normalize import _converter

            country_window = CountryAnalysisWindow()
            try:
                country_window.show()
                app.processEvents()
                country_input = work / 'country-synthetic.csv'
                with country_input.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['Address', 'Control no'])
                    for index, address in enumerate(('Hong Kong', 'China', 'Japan', ''), 1):
                        writer.writerow([address, f'{index:04d}'])
                country_report = analyze_job(
                    country_input, work / 'country-output', geo_db,
                    {'address_columns': ['Address']})
                report['country_analysis'] = {
                    'window_shown': country_window.isVisible(),
                    'mapping_entries': len(load_country_codes().entries),
                    'total_records': country_report['total_records'],
                    'destination_counts': country_report['destination_counts'],
                    'unresolved': country_report['status_counts']['UNRESOLVED'],
                    'normalization_loaded': all(_converter(kind) is not None
                                                for kind in ('t2s', 's2t')),
                }
            finally:
                country_window.close()
                app.processEvents()
    finally:
        window.close()
        app.processEvents()
    report['ok'] = True
    report['assertion_failures'] = []
    report['assertion_failures'] = report_errors(report, expected_version=project_version)
    report['ok'] = not report['assertion_failures']
    return report


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == '--self-test':
        parser = argparse.ArgumentParser(description='Offline bundle self-test')
        parser.add_argument('--self-test', action='store_true')
        parser.add_argument('--report-file', type=Path, required=True)
        args = parser.parse_args(argv)
        try:
            report = self_test()
        except Exception as exc:
            report = {'schema_version': 1, 'ok': False,
                      'error': f'{type(exc).__name__}: {exc}'}
        args.report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                    encoding='utf-8')
        return 0 if report['ok'] is True else 1
    from world_address_engine.gui.app import main as gui_main
    return gui_main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
