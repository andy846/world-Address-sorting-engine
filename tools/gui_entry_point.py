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
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from time import monotonic, sleep

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
    expected_feedback = {'icon_loaded': True, 'stage_events_observed': True,
                         'address_line_order_preserved': True,
                         'workbench_ready': True,
                         'summary_total': '4', 'summary_pending': '1',
                         'pending_rows': 1, 'first_pending_record': '4'}
    if report.get('gui_feedback') != expected_feedback:
        errors.append('gui_feedback')
    expected_regional = {
        'default_disabled': True, 'selected_path_used': True,
        'same_address_positive': True, 'number_mismatch_negative': True,
        'gui_complete': True, 'destination_counts': {'HK': 1},
        'unresolved': 1, 'version_displayed': True,
        'partial_source_displayed': True, 'quarantine_identity_pinned': True,
    }
    regional = report.get('hk_regional')
    if (not isinstance(regional, dict) or regional.keys() != expected_regional.keys()
            or any(type(regional[key]) is not type(value) or regional[key] != value
                   for key, value in expected_regional.items())):
        errors.append('hk_regional')
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


def _synthetic_geo_pack(path):
    """Empty global fixture using the builder's supported eight/four columns."""
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
        CREATE TABLE geo_places(place_id INTEGER PRIMARY KEY,name TEXT NOT NULL,
          country_code TEXT NOT NULL,admin1_code TEXT NOT NULL,admin2_code TEXT NOT NULL,
          feature_class TEXT NOT NULL,feature_code TEXT NOT NULL,population INTEGER NOT NULL);
        CREATE TABLE geo_aliases(place_id INTEGER NOT NULL,alias TEXT NOT NULL,
          search_key TEXT NOT NULL,language TEXT NOT NULL,UNIQUE(place_id,search_key));
        CREATE INDEX geo_alias_search ON geo_aliases(search_key);
        CREATE TABLE pack_metadata(profile TEXT NOT NULL);
        INSERT INTO pack_metadata VALUES('EXTENDED_GLOBAL');
        ''')


def _regional_self_test(app, window, work):
    """Create a tiny runtime-only fixture; never import the ALS pack builder."""
    from world_address_engine.data.hk_regional import alias_anchor, normalize_hk_key
    from world_address_engine.matching.hk_regional import HKRegionalMatcher

    root = work / 'regional'
    root.mkdir()
    path = root / 'pack.db'
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
        CREATE TABLE hk_buildings(csu_id TEXT PRIMARY KEY);
        CREATE TABLE hk_addresses(address_id TEXT PRIMARY KEY,csu_id TEXT NOT NULL,
          source_member TEXT NOT NULL,source_index INTEGER NOT NULL,geo_address TEXT,
          longitude REAL,latitude REAL,region_en TEXT,region_hant TEXT,district_en TEXT,
          district_hant TEXT,number_from TEXT,number_to TEXT,number_conflict INTEGER NOT NULL,
          FOREIGN KEY(csu_id) REFERENCES hk_buildings(csu_id));
        CREATE TABLE hk_aliases(address_id TEXT,kind TEXT,language TEXT,name TEXT,
          search_key TEXT,derived INTEGER,anchor TEXT,
          PRIMARY KEY(address_id,kind,language,search_key),
          FOREIGN KEY(address_id) REFERENCES hk_addresses(address_id));
        CREATE INDEX hk_alias_lookup ON hk_aliases(search_key,kind,address_id);
        CREATE INDEX hk_alias_anchor ON hk_aliases(anchor,address_id);
        CREATE INDEX hk_alias_address ON hk_aliases(address_id);
        CREATE TABLE hk_pack_metadata(profile TEXT,schema_version INTEGER,normalization_version INTEGER);
        INSERT INTO hk_pack_metadata VALUES('HK_BILINGUAL_REGIONAL',1,1);
        INSERT INTO hk_buildings VALUES('SYNTHETIC-CSU');
        INSERT INTO hk_addresses VALUES('synthetic-address','SYNTHETIC-CSU','synthetic.geojson',1,
          NULL,114.1,22.3,NULL,NULL,NULL,NULL,'10','20',0);
        ''')
        for kind, name in (('building', 'Lantern Building'), ('street', 'Orchid Road')):
            key = normalize_hk_key(name)
            db.execute('INSERT INTO hk_aliases VALUES(?,?,?,?,?,?,?)',
                       ('synthetic-address', kind, 'en', name, key, 0, alias_anchor(key)))
    quarantine = (json.dumps({'source_member': 'synthetic.geojson', 'source_index': 2,
                              'reason': 'feature_schema'}) + '\n').encode('utf-8')
    (root / 'quarantine.jsonl').write_bytes(quarantine)
    source_validation = {
        'policy': 'quarantine-invalid', 'coverage': 'partial',
        'feature_count': 2, 'valid_feature_count': 1, 'quarantined_feature_count': 1,
        'quarantine_file': 'quarantine.jsonl',
        'quarantine_sha256': hashlib.sha256(quarantine).hexdigest(),
    }
    metadata = {
        'profile': 'HK_BILINGUAL_REGIONAL', 'schema_version': 1, 'normalization_version': 1,
        'pack_id': 'hk-bilingual-als', 'pack_version': 'synthetic-smoke-1',
        'source_date': '2026-10-24', 'source_url': 'https://www.als.gov.hk/',
        'source_sha256': '0' * 64, 'schema_sha256': '1' * 64,
        'db_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'record_count': 1, 'building_count': 1, 'alias_count': 2,
        'alias_count_by_language': {'en': 2}, 'conversion_version': 'synthetic-no-conversion',
        'attribution': 'Synthetic fixture only; not official address data',
        'license': 'Synthetic self-test fixture',
        'source_validation': source_validation,
    }
    (root / 'manifest.json').write_text(json.dumps(metadata), encoding='utf-8')
    positive, negative = 'Lantern Building\n12 Orchid Road', 'Lantern Building\n99 Orchid Road'
    with HKRegionalMatcher(path) as matcher:
        match = matcher.match(positive)
        same_address = match is not None and match.address_ids == ('synthetic-address',)
        mismatch = matcher.match(negative) is None

    # Empty, structurally valid global tables ensure that HK comes only from
    # the explicitly selected regional pack, with no real data bundled.
    geo = work / 'regional-global.db'
    _synthetic_geo_pack(geo)
    source, output = work / 'regional-input.csv', work / 'regional-output'
    with source.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Address'])
        writer.writerows(((positive,), (negative,)))
    default_disabled = not window.hk_enabled.isChecked()
    window.input_path.setText(str(source))
    window.address_columns.addItem('Address')
    window.address_columns.item(0).setSelected(True)
    window.geo_db.setText(str(geo))
    window.output_dir.setText(str(output))
    window.hk_regional_db.setText(str(path))
    window.hk_enabled.setChecked(True)
    window.start_job()
    deadline = monotonic() + 30
    while window.busy and monotonic() < deadline:
        app.processEvents()
        sleep(.005)
    if window.busy:
        window.cancel_job()
        window.worker_thread.wait(10_000)
        app.processEvents()
        raise TimeoutError('Regional GUI self-test did not complete in time')
    app.processEvents()
    result = window._last_report or {}
    regional = result.get('run_metadata', {}).get('hk_regional') or {}
    return {
        'default_disabled': default_disabled,
        'selected_path_used': (regional.get('path') == str(path.resolve())
                               and regional.get('profile') == 'HK_BILINGUAL_REGIONAL'),
        'same_address_positive': same_address, 'number_mismatch_negative': mismatch,
        'gui_complete': window.job_state == 'done',
        'destination_counts': result.get('destination_counts'),
        'unresolved': result.get('status_counts', {}).get('UNRESOLVED'),
        'version_displayed': 'Hong Kong: synthetic-smoke-1' in window.source_versions.text(),
        'partial_source_displayed': ('Hong Kong: synthetic-smoke-1 (partial source; 1 excluded)'
                                     in window.source_versions.text()),
        'quarantine_identity_pinned': regional.get('source_validation') == source_validation,
    }


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
            _synthetic_geo_pack(geo_db)
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
            from world_address_engine.gui.country_app import CountryAnalysisWindow, _read_country_export
            from world_address_engine.jobs.country_analysis import analyze_job
            from world_address_engine.matching.normalize import _converter

            country_window = CountryAnalysisWindow()
            try:
                line_columns = ['Line 1', 'Line 2', 'Line 3']
                country_window.address_columns.addItems(line_columns)
                for index in (1, 2, 0):
                    country_window.address_columns.item(index).setSelected(True)
                line_order_preserved = country_window._input_options()['address_columns'] == line_columns
                country_window.address_columns.clear()
                country_window.show()
                app.processEvents()
                workbench_ready = (
                    country_window.workbench.count() == 2
                    and country_window.workbench.widget(0) is country_window.settings_scroll
                    and country_window.settings_scroll.widget() is country_window.inputs
                    and country_window.appearance.isVisible()
                    and {country_window.appearance.itemData(i)
                         for i in range(country_window.appearance.count())} == {'system', 'light', 'dark'}
                    and not country_window.diagnostics.isVisible())
                country_input = work / 'country-synthetic.csv'
                with country_input.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['Address', 'Control no'])
                    for index, address in enumerate(('Hong Kong', 'China', 'Japan', ''), 1):
                        writer.writerow([address, f'{index:04d}'])
                stage_events = []
                country_output = work / 'country-output'
                country_report = analyze_job(
                    country_input, country_output, geo_db,
                    {'address_columns': ['Address']}, on_event=stage_events.append)
                country_window._output_dir = country_output
                country_window._apply_analysis(_read_country_export(country_output, country_report))
                app.processEvents()
                stages = {event['stage'] for event in stage_events}
                panel = country_window.results
                workbench_ready = (workbench_ready
                                   and len(panel.metric_cards) == 4
                                   and '4' in panel.total_value.accessibleName()
                                   and '1' in panel.pending_value.accessibleName())
                report['gui_feedback'] = {
                    'icon_loaded': not country_window.windowIcon().isNull(),
                    'address_line_order_preserved': line_order_preserved,
                    'workbench_ready': workbench_ready,
                    'stage_events_observed': {'validating', 'hashing_pack', 'classifying',
                                              'exporting', 'finalizing', 'complete'} <= stages,
                    'summary_total': panel.total_value.text(),
                    'summary_pending': panel.pending_value.text(),
                    'pending_rows': panel.case_table.rowCount(),
                    'first_pending_record': panel.case_table.item(0, 0).text()
                    if panel.case_table.rowCount() else None,
                }
                report['country_analysis'] = {
                    'window_shown': country_window.isVisible(),
                    'mapping_entries': len(load_country_codes().entries),
                    'total_records': country_report['total_records'],
                    'destination_counts': country_report['destination_counts'],
                    'unresolved': country_report['status_counts']['UNRESOLVED'],
                    'normalization_loaded': all(_converter(kind) is not None
                                                for kind in ('t2s', 's2t')),
                }
                report['hk_regional'] = _regional_self_test(app, country_window, work)
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
