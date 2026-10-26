"""Packaging checks exercise reports and archives without building a real bundle."""

import builtins
import csv
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import threading
import tomllib
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'tools'))

import gui_entry_point as entry  # noqa: E402
import package_windows as packaging  # noqa: E402


WORKFLOW_V03 = {
    'report_schema_version': 2,
    'generated_columns': ['Country_Code', 'Zone_Code', 'NOVSN_Zone_Code'],
    'detail_header': ['Address', 'Control no', 'Country_Code', 'Zone_Code', 'NOVSN_Zone_Code'],
    'detail_rows': [['Hong Kong', '0001', 'HK', 'LOCAL', 'A'],
                    ['China', '0002', 'CN', 'CN - Airmail', 'F'],
                    ['Japan', '0003', 'JP', '2', 'D'], ['', '0004', '', '', '']],
    'summary_header': ['Country_Code', 'Country_Name_TC', 'Country_Name_EN',
                       'Zone_Code', 'NOVSN_Zone_Code', 'Count', 'Percentage'],
    'summary_zones': [['CN', 'CN - Airmail', 'F'], ['HK', 'LOCAL', 'A'],
                      ['JP', '2', 'D'], ['', '', '']],
    'auto_output_child': True,
    'native_pages': True,
    'quick_ready': True,
    'quick_result': {'code': 'HK', 'zone': 'LOCAL', 'novsn': 'A', 'copy_enabled': True},
    'quick_clear_invalidates': True,
}


def test_self_test_isolates_settings_discovery_and_drains_before_cleanup(monkeypatch):
    pytest.importorskip('PySide6')
    from PySide6 import QtCore
    from world_address_engine.gui import country_app, country_paths
    from world_address_engine.gui.app import _LIVE_THREADS

    def forbidden(*args, **kwargs):
        raise AssertionError('self-test must isolate native preferences and installed packs')

    original_settings = QtCore.QSettings
    original_temp = entry.tempfile.TemporaryDirectory
    settings_paths, roots_seen, threads = [], [], []
    original_build = country_app.CountryAnalysisWindow._build

    def settings(path, format):
        assert Path(path).name == 'self-test.ini'
        assert format == original_settings.Format.IniFormat
        settings_paths.append(Path(path))
        return original_settings(path, format)

    settings.Format = original_settings.Format

    def build(window):
        roots_seen.append(country_paths.discovery_roots())
        original_build(window)
        threads.append(window._lookup_thread)

    class CheckedCleanup(original_temp):
        def cleanup(self):
            if Path(self.name).name.startswith('wase-self-test-'):
                assert all(not thread.isRunning() for thread in threads)
                assert not (set(threads) & _LIVE_THREADS)
                assert country_app.QSettings is forbidden
                assert country_paths.discovery_roots is forbidden
            super().cleanup()

    monkeypatch.setattr(country_app, 'QSettings', forbidden)
    monkeypatch.setattr(country_paths, 'discovery_roots', forbidden)
    monkeypatch.setattr(QtCore, 'QSettings', settings)
    monkeypatch.setattr(country_app.CountryAnalysisWindow, '_build', build)
    monkeypatch.setattr(entry.tempfile, 'TemporaryDirectory', CheckedCleanup)
    report = entry.self_test()
    assert report['ok'] is True
    assert settings_paths and all(path == settings_paths[0] for path in settings_paths)
    assert roots_seen == [(settings_paths[0].parent,)]
    assert not settings_paths[0].parent.exists()


@pytest.mark.parametrize('field', [*WORKFLOW_V03, None])
@pytest.mark.parametrize('fault', ['missing', 'false', 'integer', 'string', 'null'])
def test_bundle_requires_strict_workflow_v03_evidence(field, fault):
    # A separately specified contract lets the gate fail RED without constructing
    # an unisolated pre-v0.3 GUI or warming any installed reference packs.
    report = {'workflow_v03': deepcopy(WORKFLOW_V03)}
    assert 'workflow_v03' not in entry.report_errors(report, expected_version='test')
    if field is None:
        report.pop('workflow_v03')
    elif fault == 'missing':
        report['workflow_v03'].pop(field)
    else:
        report['workflow_v03'][field] = {'false': False, 'integer': 1,
                                          'string': 'true', 'null': None}[fault]
    assert 'workflow_v03' in entry.report_errors(report, expected_version='test')


def test_bundle_rejects_extra_workflow_claims_and_nested_type_coercion():
    for field, value in [('extra', True), ('quick_result',
                         {'code': 'HK', 'zone': 'LOCAL', 'novsn': 'A', 'copy_enabled': 1})]:
        report = {'workflow_v03': deepcopy(WORKFLOW_V03)}
        report['workflow_v03'][field] = value
        assert 'workflow_v03' in entry.report_errors(report, expected_version='test')


def test_bundle_proves_v03_exports_and_native_quick_workflow(runtime_report):
    assert runtime_report['workflow_v03'] == WORKFLOW_V03


@pytest.mark.parametrize('pause_at', ['warm_ready', 'query_ready', 'query_result'])
def test_v03_smoke_waits_for_real_worker_query_generation(monkeypatch, pause_at):
    """Ready before settled, or another generation's signals, cannot end the wait."""
    pytest.importorskip('PySide6')
    from PySide6.QtCore import Qt

    original = entry._workflow_self_test
    observations = []

    def paused_workflow(app, window, output, work):
        worker = window._lookup_thread
        paused, release = threading.Event(), threading.Event()
        window._pack_timer.stop()
        window._lookup_generation += 1
        warm_generation = window._lookup_generation
        query_generation = None
        window._lookup_ready = False
        window.quick.query.setEnabled(False)

        submit = worker.submit

        def track_submit(generation, config, text=None):
            nonlocal query_generation
            if text is not None:
                query_generation = generation
            submit(generation, config, text)

        monkeypatch.setattr(worker, 'submit', track_submit)

        def pause(generation, *args):
            target = warm_generation if pause_at == 'warm_ready' else query_generation
            if generation == target and (pause_at == 'query_result' or args[0]):
                paused.set()
                release.wait(10)

        signal = worker.result if pause_at == 'query_result' else worker.state
        signal.connect(pause, Qt.ConnectionType.DirectConnection)
        pumps = 0

        def process_events():
            nonlocal pumps
            app.processEvents()
            if paused.is_set() and window._lookup_ready:
                pumps += 1
                if pumps == 1 and pause_at != 'warm_ready':
                    # Both old and warm completions are unrelated to this query.
                    worker.result.emit(warm_generation, {
                        'code': 'JP', 'name': 'Japan', 'status': 'DETERMINED',
                        'zone': '2', 'novsn': 'D'})
                    worker.settled.emit(warm_generation - 1)
                    worker.settled.emit(warm_generation)
                    if pause_at == 'query_ready':
                        # Even matching completion cannot replace a matching result.
                        worker.settled.emit(query_generation)
                elif pumps >= 5:
                    release.set()

        try:
            window._warm_lookup()
            if pause_at != 'warm_ready':
                deadline = entry.monotonic() + 5
                while not (window._lookup_ready and window.quick.query.isEnabled()):
                    assert entry.monotonic() < deadline, 'real worker did not warm'
                    app.processEvents()
                    entry.sleep(.005)
            evidence = original(SimpleNamespace(processEvents=process_events), window, output, work)
            observations.append((paused.is_set(), release.is_set()))
            return evidence
        finally:
            release.set()
            signal.disconnect(pause)

    monkeypatch.setattr(entry, '_workflow_self_test', paused_workflow)
    report = entry.self_test()
    assert report['workflow_v03'] == WORKFLOW_V03
    assert report['ok'] is True
    assert observations == [(True, True)], 'workflow returned before the real worker was released'


@pytest.mark.parametrize('failure', ['schema', 'generated_columns', 'detail_header',
                                    'original_cell', 'hk_zone', 'cn_zone', 'jp_novsn',
                                    'unresolved_country', 'unresolved_zone', 'unresolved_novsn',
                                    'summary_header', 'summary_zone'])
def test_v03_smoke_reads_actual_published_export_bytes(monkeypatch, failure):
    pytest.importorskip('PySide6')
    from world_address_engine.jobs import country_analysis
    original = country_analysis.analyze_job

    def corrupt(source, output, *args, **kwargs):
        report = original(source, output, *args, **kwargs)
        if Path(source).name != 'country-synthetic.csv':
            return report
        output = Path(output)
        if failure in ('schema', 'generated_columns'):
            path = output / 'Run_Manifest.json'
            manifest = json.loads(path.read_text('utf-8'))
            if failure == 'schema':
                manifest['report_schema_version'] = 1
            else:
                manifest['generated_columns'] = ['Country_Code', 'NOVSN_Zone_Code', 'Zone_Code']
            # Leave the API return intact: the smoke must read the published file.
            path.write_text(json.dumps(manifest), encoding='utf-8')
        else:
            summary = failure.startswith('summary_')
            path = output / ('Country_Summary.csv' if summary else 'Classified_Addresses.csv')
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.reader(stream))
            row, col = {'detail_header': (0, 3), 'original_cell': (1, 1),
                        'hk_zone': (1, 3), 'cn_zone': (2, 3), 'jp_novsn': (3, 4),
                        'unresolved_country': (4, 2), 'unresolved_zone': (4, 3),
                        'unresolved_novsn': (4, 4), 'summary_header': (0, 3),
                        'summary_zone': (1, 3)}[failure]
            rows[row][col] = 'BROKEN'
            with path.open('w', encoding='utf-8-sig', newline='') as stream:
                csv.writer(stream).writerows(rows)
        return report

    monkeypatch.setattr(country_analysis, 'analyze_job', corrupt)
    report = entry.self_test()
    assert report['ok'] is False
    assert 'workflow_v03' in report['assertion_failures']


@pytest.mark.parametrize('failure', ['auto_output', 'page_name', 'batch_default',
                                    'quick_code', 'quick_zone', 'quick_novsn',
                                    'quick_copy', 'clear_invalidation', 'default_hk'])
def test_v03_smoke_rejects_broken_native_workflow(monkeypatch, failure):
    pytest.importorskip('PySide6')
    from world_address_engine.gui import country_app, country_lookup
    if failure == 'auto_output':
        def exact_parent(source, parent):
            parent = Path(parent)
            parent.mkdir(parents=True, exist_ok=True)
            return parent.resolve()
        monkeypatch.setattr(country_app, 'allocate_run_directory', exact_parent)
    elif failure in ('page_name', 'batch_default', 'default_hk'):
        original = country_app.CountryAnalysisWindow._build
        def build(window):
            original(window)
            if failure == 'page_name':
                window.pages.setTabText(1, 'Single address')
            elif failure == 'batch_default':
                window.pages.setCurrentIndex(1)
            else:
                window.hk_enabled.setChecked(False)
        monkeypatch.setattr(country_app.CountryAnalysisWindow, '_build', build)
    elif failure == 'clear_invalidation':
        original = country_lookup.QuickLookupPanel.invalidate
        def invalidate(panel):
            if panel.address.toPlainText():
                original(panel)
        monkeypatch.setattr(country_lookup.QuickLookupPanel, 'invalidate', invalidate)
    else:
        original = country_lookup.QuickLookupPanel.show_result
        def show(panel, payload):
            payload = dict(payload)
            if failure != 'quick_copy':
                payload[failure.removeprefix('quick_')] = 'BROKEN'
            original(panel, payload)
            if failure == 'quick_copy':
                panel.copy.setEnabled(False)
        monkeypatch.setattr(country_lookup.QuickLookupPanel, 'show_result', show)
    report = entry.self_test()
    assert report['ok'] is False
    assert ('hk_regional' if failure == 'default_hk' else 'workflow_v03') in report['assertion_failures']


def test_self_test_restores_isolation_after_batch_exception(monkeypatch):
    pytest.importorskip('PySide6')
    from world_address_engine.gui import country_app, country_paths
    from world_address_engine.gui.app import _LIVE_THREADS
    settings, roots = country_app.QSettings, country_paths.discovery_roots
    original = country_app.CountryAnalysisWindow.start_job
    original_temp = entry.tempfile.TemporaryDirectory
    windows, checked = [], []

    def fail_after_start(window):
        original(window)
        windows.append(window)
        assert window.busy
        raise RuntimeError('injected failure after batch launch')

    class CheckedCleanup(original_temp):
        def cleanup(self):
            if Path(self.name).name.startswith('wase-self-test-'):
                assert country_app.QSettings is settings
                assert country_paths.discovery_roots is roots
                assert windows
                window = windows[0]
                assert not window.busy
                for thread in (window.worker_thread, window._lookup_thread):
                    assert not thread.isRunning()
                    assert thread not in _LIVE_THREADS
                checked.append(self.name)
            super().cleanup()

    monkeypatch.setattr(country_app.CountryAnalysisWindow, 'start_job', fail_after_start)
    monkeypatch.setattr(entry.tempfile, 'TemporaryDirectory', CheckedCleanup)
    with pytest.raises(RuntimeError, match='injected failure after batch launch'):
        entry.self_test()
    assert checked and not Path(checked[0]).exists()


def test_packaging_extra_supplies_the_builder():
    project = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text('utf-8'))
    from packaging.requirements import Requirement
    requirements = [Requirement(item) for item in
                    project['project']['optional-dependencies'].get('packaging', [])]
    builder = next((r for r in requirements if r.name.lower() == 'pyinstaller'), None)
    assert builder is not None
    assert '6.0' in builder.specifier
    assert '7.0' not in builder.specifier
    assert '5.13' not in builder.specifier


def test_the_build_fails_clearly_without_pyinstaller(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def missing_builder(name, *args, **kwargs):
        if name == 'PyInstaller':
            raise ImportError('no pyinstaller here')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', missing_builder)
    with pytest.raises(SystemExit, match='PyInstaller'):
        packaging.build(tmp_path)


def _fake_builder(monkeypatch, *, archive_names=(), tree_names=()):
    # Write real CArchives; only the expensive external build is substituted.
    writer = pytest.importorskip('PyInstaller.archive.writers').CArchiveWriter
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        output = Path(command[command.index('--distpath') + 1])
        root = output if '--onefile' in command else output / packaging.APP_NAME
        root.mkdir(parents=True, exist_ok=True)
        payload = output / 'archive-payload'
        payload.write_bytes(b'synthetic payload')
        executable = root / f'{packaging.APP_NAME}.exe'
        writer(str(executable), [(name, str(payload), True, 'x')
                                 for name in archive_names], 'python313.dll')
        for name in tree_names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'synthetic payload')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(packaging.subprocess, 'run', run)
    return commands


@pytest.mark.parametrize('onefile', [True, False])
def test_build_returns_executable_and_keeps_runtime_metadata(monkeypatch, tmp_path, onefile):
    commands = _fake_builder(monkeypatch, archive_names=('PySide6/plugins/platforms/qoffscreen.dll',))
    executable = packaging.build(tmp_path, onefile=onefile)
    assert executable.is_file()
    assert executable.name == f'{packaging.APP_NAME}.exe'
    command = commands[0]
    assert '--copy-metadata' in command
    assert command[command.index('--copy-metadata') + 1] == 'world-address-sorting-engine'
    assert 'world_address_engine.data.geonames_builder' not in command


@pytest.mark.skipif(os.name != 'nt', reason='Windows DLL resolution')
def test_builder_resolves_system_icu_despite_a_polluted_parent_path(monkeypatch, tmp_path):
    pytest.importorskip('PyInstaller')
    real_run = subprocess.run
    _fake_builder(monkeypatch)
    fake_run = packaging.subprocess.run
    polluted = tmp_path / 'unrelated-native-tools'
    polluted.mkdir()
    (polluted / 'icuuc.dll').write_bytes(
        (Path(os.environ['SystemRoot']) / 'System32' / 'icuuc.dll').read_bytes())
    parent_path = str(polluted) + os.pathsep + os.environ.get('PATH', '')
    monkeypatch.setenv('PATH', parent_path)
    resolved = []

    def inspect_environment(command, **kwargs):
        probe = real_run(
            [sys.executable, '-c',
             'from PyInstaller.depend.bindepend import resolve_library_path; '
             'print(resolve_library_path("icuuc.dll"))'],
            env=kwargs.get('env'), capture_output=True, text=True, check=True)
        resolved.append(Path(probe.stdout.strip()))
        return fake_run(command, **kwargs)

    monkeypatch.setattr(packaging.subprocess, 'run', inspect_environment)
    packaging.build(tmp_path / 'output')
    assert resolved == [Path(os.environ['SystemRoot']) / 'System32' / 'icuuc.dll']
    assert os.environ['PATH'] == parent_path


@pytest.mark.parametrize('onefile', [True, False])
@pytest.mark.parametrize('name', ['data/compact_global.sqlite', r'data\PACK.DB',
                                 'Geonames-private/payload.bin',
                                 'data/compact_global.sqlite.zip',
                                 r'data\EXTENDED_GLOBAL.SQLITE.ZIP'])
def test_build_rejects_reference_payloads_in_carchive(monkeypatch, tmp_path, onefile, name):
    _fake_builder(monkeypatch, archive_names=(name,))
    with pytest.raises(SystemExit, match='reference'):
        packaging.build(tmp_path, onefile=onefile)


@pytest.mark.parametrize('name', ['_internal/packs/extended.sqlite', '_internal/PACK.DB',
                                 '_internal/geonames-secret/payload.bin',
                                 '_internal/compact_global.sqlite.zip',
                                 '_internal/extended_global.sqlite.zip'])
def test_build_rejects_reference_payloads_in_onedir_tree(monkeypatch, tmp_path, name):
    _fake_builder(monkeypatch, tree_names=(name,))
    with pytest.raises(SystemExit, match='reference'):
        packaging.build(tmp_path, onefile=False)


def test_build_rejects_an_unreadable_archive(monkeypatch, tmp_path):
    def run(command, **kwargs):
        (tmp_path / f'{packaging.APP_NAME}.exe').write_bytes(b'not an archive')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(packaging.subprocess, 'run', run)
    with pytest.raises(SystemExit, match='archive'):
        packaging.build(tmp_path)


@pytest.fixture(scope='module')
def runtime_report():
    pytest.importorskip('PySide6')
    return entry.self_test()


def test_self_test_exercises_the_window_runner_and_previews(runtime_report):
    assert isinstance(runtime_report, dict)
    assert runtime_report['ok'] is True
    assert runtime_report['window_shown'] is True
    assert runtime_report['events_processed'] is True
    assert runtime_report['classification_attempted'] is True
    assert runtime_report['approval_refused'] is True
    assert runtime_report['classification_output_created'] is False
    assert runtime_report['approved_codes'] == {}
    assert runtime_report['review_codes'] == 0
    preview = runtime_report['preview']
    assert preview['total_records'] == 9604
    assert preview['original_columns'] == 12
    assert preview['records_with_extra_unnamed_data'] == 1
    assert preview['classifications_run'] is False
    assert runtime_report['xlsx_preview']['total_records'] == 1
    assert runtime_report['xlsx_preview']['classifications_run'] is False
    project = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text('utf-8'))
    assert runtime_report['version'] == project['project']['version']


def test_self_test_reports_the_running_code_version_not_stale_installed_metadata(monkeypatch):
    """The bundle must attest to the code that is running, not to install metadata.

    An editable or stale install leaves ``importlib.metadata`` pointing at an
    older release, which previously made the self-test report a version that
    the running code did not actually have.
    """
    pytest.importorskip('PySide6')
    import world_address_engine

    monkeypatch.setattr(entry, 'version', lambda name: '0.0.0-stale-install-metadata')
    report = entry.self_test()
    assert isinstance(report, dict)
    assert report['version'] == world_address_engine.__version__
    assert report['version'] != '0.0.0-stale-install-metadata'
    assert report['ok'] is True


def test_the_release_version_authority_is_consistent():
    """pyproject, the package and the packaged bundle must agree on one version."""
    import world_address_engine

    project = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text('utf-8'))
    assert project['project']['version'] == world_address_engine.__version__
    assert packaging.project_version() == world_address_engine.__version__


def test_bundle_exercises_default_country_gui_and_bundled_mapping():
    pytest.importorskip('PySide6')
    report = entry.self_test()
    assert report['country_analysis']['window_shown'] is True
    assert report['country_analysis']['mapping_entries'] == 235
    assert report['country_analysis']['total_records'] == 4
    assert report['country_analysis']['destination_counts'] == {'CN': 1, 'HK': 1, 'JP': 1}
    assert report['country_analysis']['unresolved'] == 1
    assert report['ok'] is True


def test_bundle_rejects_missing_country_analysis_evidence(runtime_report):
    report = dict(runtime_report)
    report.pop('country_analysis', None)
    assert 'country_analysis' in entry.report_errors(report, expected_version=packaging.project_version())


def test_bundle_proves_optional_regional_api_and_selected_gui_path(runtime_report):
    assert runtime_report['hk_regional'] == {
        'default_enabled': True, 'selected_path_used': True,
        'same_address_positive': True, 'number_mismatch_negative': True,
        'gui_complete': True, 'destination_counts': {'HK': 1},
        'unresolved': 1, 'version_displayed': True,
        'partial_source_displayed': True, 'quarantine_identity_pinned': True,
    }


def test_regional_smoke_uses_a_verified_partial_runtime_fixture(tmp_path):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from world_address_engine.data.hk_regional import verify_hk_pack

    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([])
    with entry._self_test_country_window(app, tmp_path) as window:
        evidence = entry._regional_self_test(app, window, tmp_path)
        root = tmp_path / 'regional'
        contents = (root / 'quarantine.jsonl').read_bytes()
        assert [json.loads(line) for line in contents.splitlines()] == [
            {'source_member': 'synthetic.geojson', 'source_index': 2, 'reason': 'feature_schema'}]
        expected = {
            'policy': 'quarantine-invalid', 'coverage': 'partial',
            'feature_count': 2, 'valid_feature_count': 1, 'quarantined_feature_count': 1,
            'quarantine_file': 'quarantine.jsonl',
            'quarantine_sha256': hashlib.sha256(contents).hexdigest(),
        }
        metadata = verify_hk_pack(root / 'pack.db')
        assert metadata['source_validation'] == expected
        with closing(sqlite3.connect(root / 'pack.db')) as db:
            assert db.execute('SELECT source_index FROM hk_addresses').fetchall() == [(1,)]
        assert window._last_report['run_metadata']['hk_regional']['source_validation'] == expected
        assert 'Hong Kong: synthetic-smoke-1 (partial source; 1 excluded)' in window.source_versions.text()
        assert evidence['partial_source_displayed'] is True
        assert evidence['quarantine_identity_pinned'] is True


def test_self_test_global_fixtures_satisfy_real_pack_validation(monkeypatch):
    pytest.importorskip('PySide6')
    from world_address_engine.jobs import country_analysis
    original = country_analysis._pack_metadata
    validated = set()

    def validate(path, digest):
        result = original(path, digest)
        validated.add(path.name)
        assert result['profile'] == 'EXTENDED_GLOBAL'
        return result

    monkeypatch.setattr(country_analysis, '_pack_metadata', validate)
    result = entry.self_test()
    assert result['ok'] is True
    assert {'synthetic-geo.db', 'regional-global.db'} <= validated


@pytest.mark.parametrize('field', ['default_enabled', 'selected_path_used',
                                 'same_address_positive', 'number_mismatch_negative',
                                 'gui_complete', 'destination_counts', 'unresolved',
                                 'version_displayed', 'partial_source_displayed',
                                 'quarantine_identity_pinned', None])
@pytest.mark.parametrize('fault', ['missing', 'false'])
def test_bundle_rejects_missing_or_false_regional_evidence(runtime_report, field, fault):
    broken = dict(runtime_report)
    if field is None:
        broken.pop('hk_regional', None)
    else:
        broken['hk_regional'] = dict(runtime_report.get('hk_regional', {}))
        if fault == 'missing':
            broken['hk_regional'].pop(field, None)
        else:
            broken['hk_regional'][field] = False
    assert 'hk_regional' in entry.report_errors(broken, expected_version=packaging.project_version())


@pytest.mark.parametrize('field', ['partial_source_displayed', 'quarantine_identity_pinned'])
@pytest.mark.parametrize('value', [0, 1, None, 'true'])
def test_bundle_requires_boolean_partial_evidence(runtime_report, field, value):
    broken = dict(runtime_report)
    broken['hk_regional'] = dict(runtime_report['hk_regional'], **{field: value})
    assert 'hk_regional' in entry.report_errors(broken, expected_version=packaging.project_version())


def test_bundle_regional_smoke_does_not_import_build_only_dependencies(monkeypatch):
    pytest.importorskip('PySide6')
    real_import = builtins.__import__

    def runtime_only(name, *args, **kwargs):
        if name.split('.')[0] in {'ijson', 'jsonschema'} or name.endswith('hk_als_builder'):
            raise AssertionError('build-only dependency imported by runtime self-test')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', runtime_only)
    result = entry.self_test()
    assert result['ok'] is True
    assert result['hk_regional']['selected_path_used'] is True


@pytest.mark.parametrize('failure', ['no_match', 'always_match', 'disabled_gui'])
def test_regional_smoke_fails_when_runtime_behavior_is_broken(monkeypatch, failure):
    pytest.importorskip('PySide6')
    from world_address_engine.matching.hk_regional import HKRegionalMatcher, HKRegionalMatch
    from world_address_engine.gui.country_app import CountryAnalysisWindow
    if failure == 'no_match':
        monkeypatch.setattr(HKRegionalMatcher, 'match', lambda *a: None)
    elif failure == 'always_match':
        monkeypatch.setattr(HKRegionalMatcher, 'match', lambda *a:
                            HKRegionalMatch(('synthetic-address',), ('street', 'building_or_estate')))
    else:
        original = CountryAnalysisWindow.start_job

        def disabled_gui(window):
            window.hk_enabled.setChecked(False)
            return original(window)

        monkeypatch.setattr(CountryAnalysisWindow, 'start_job', disabled_gui)
    result = entry.self_test()
    assert result['ok'] is False
    assert 'hk_regional' in result['assertion_failures']


@pytest.mark.parametrize('failure', ['partial_label', 'missing_identity', 'changed_hash', 'extra_identity_field'])
def test_regional_smoke_rejects_broken_partial_display_or_quarantine_identity(monkeypatch, failure):
    pytest.importorskip('PySide6')
    from world_address_engine.gui.country_app import CountryAnalysisWindow
    original = CountryAnalysisWindow._apply_analysis

    def corrupt_partial_evidence(window, payload):
        original(window, payload)
        regional = (window._last_report or {}).get('run_metadata', {}).get('hk_regional')
        if not regional:
            return
        if failure == 'partial_label':
            window.source_versions.setText(window.source_versions.text().replace(
                ' (partial source; 1 excluded)', ''))
        elif failure == 'missing_identity':
            regional.pop('source_validation', None)
        else:
            validation = dict(regional.get('source_validation', {}))
            if failure == 'changed_hash':
                validation['quarantine_sha256'] = 'f' * 64
            else:
                validation['unexpected'] = True
            regional['source_validation'] = validation

    monkeypatch.setattr(CountryAnalysisWindow, '_apply_analysis', corrupt_partial_evidence)
    result = entry.self_test()
    assert result['ok'] is False
    assert 'hk_regional' in result['assertion_failures']
    evidence = 'partial_source_displayed' if failure == 'partial_label' else 'quarantine_identity_pinned'
    assert result['hk_regional'][evidence] is False


def test_bundle_proves_icon_progress_and_completed_pending_case_view(runtime_report):
    feedback = runtime_report['gui_feedback']
    assert feedback == {'icon_loaded': True, 'stage_events_observed': True,
                        'address_line_order_preserved': True,
                        'workbench_ready': True,
                        'summary_total': '4', 'summary_pending': '1',
                        'pending_rows': 1, 'first_pending_record': '4'}
    broken = dict(runtime_report)
    broken.pop('gui_feedback')
    assert 'gui_feedback' in entry.report_errors(broken, expected_version=packaging.project_version())


def test_frozen_self_test_proves_click_order_does_not_reorder_address_lines(runtime_report):
    assert runtime_report['gui_feedback']['address_line_order_preserved'] is True
    broken = dict(runtime_report)
    broken['gui_feedback'] = dict(runtime_report['gui_feedback'], address_line_order_preserved=False)
    assert 'gui_feedback' in entry.report_errors(broken, expected_version=packaging.project_version())


def test_frozen_self_test_proves_native_workbench_and_hidden_diagnostics(runtime_report):
    assert runtime_report['gui_feedback']['workbench_ready'] is True
    broken = dict(runtime_report)
    broken['gui_feedback'] = dict(runtime_report['gui_feedback'], workbench_ready=False)
    assert 'gui_feedback' in entry.report_errors(broken, expected_version=packaging.project_version())


def test_frozen_workbench_gate_rejects_metric_names_without_the_numbers(monkeypatch):
    pytest.importorskip('PySide6')
    from world_address_engine.gui.country_results import CountryResultsPanel
    original = CountryResultsPanel._set_metric_value

    def missing_number(panel, name, text):
        original(panel, name, text)
        getattr(panel, f'{name}_value').setAccessibleName(panel._metric_captions[name])

    monkeypatch.setattr(CountryResultsPanel, '_set_metric_value', missing_number)
    report = entry.self_test()
    assert report['ok'] is False
    assert 'gui_feedback' in report['assertion_failures']


def test_bundle_requires_offline_chinese_normalization_data(monkeypatch):
    pytest.importorskip('PySide6')
    from world_address_engine.matching import normalize
    monkeypatch.setattr(normalize, '_converter', lambda kind: None)
    report = entry.self_test()
    assert report['ok'] is False
    assert 'country_analysis' in report['assertion_failures']


@pytest.mark.parametrize('name', ['nested/hidden.sqlite', 'nested/PACK.DB',
                                 'Geonames-secret/payload',
                                 'nested/compact_global.sqlite.zip',
                                 'nested/extended_global.sqlite.zip'])
def test_runtime_probes_the_actual_extraction_tree(monkeypatch, tmp_path, name):
    pytest.importorskip('PySide6')
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'synthetic payload')
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    report = entry.self_test()
    assert isinstance(report, dict)
    assert report['pack_bundled'] is True
    assert report['ok'] is False


@pytest.mark.parametrize('failure', ['accepted', 'unrelated-error'])
def test_self_test_rejects_a_missing_or_wrong_approval_refusal(monkeypatch, failure):
    pytest.importorskip('PySide6')
    from world_address_engine.jobs import runner

    def broken_runner(*args, **kwargs):
        if failure == 'unrelated-error':
            raise ValueError('an unrelated failure')
        return {'job_state': 'complete'}

    monkeypatch.setattr(runner, 'run_job', broken_runner)
    report = entry.self_test()
    assert isinstance(report, dict)
    assert report['classification_attempted'] is True
    assert report['approval_refused'] is False
    assert report['ok'] is False


def test_self_test_rejects_incorrect_preview_results(monkeypatch):
    pytest.importorskip('PySide6')
    from world_address_engine import cli
    monkeypatch.setattr(cli, 'preview', lambda *a, **kw: {'total_records': 0})
    report = entry.self_test()
    assert isinstance(report, dict)
    assert report['ok'] is False


def test_main_writes_report_without_stdout(monkeypatch, tmp_path):
    pytest.importorskip('PySide6')
    monkeypatch.setattr(sys, 'stdout', None)
    report_path = tmp_path / 'self-test.json'
    assert entry.main(['--self-test', '--report-file', str(report_path)]) == 0
    report = json.loads(report_path.read_text('utf-8'))
    assert report['ok'] is True
    assert report['schema_version'] == 1


def test_main_reports_unexpected_self_test_failure(monkeypatch, tmp_path):
    def fail():
        raise RuntimeError('missing bundled dependency')

    monkeypatch.setattr(entry, 'self_test', fail)
    report_path = tmp_path / 'failure.json'
    assert entry.main(['--self-test', '--report-file', str(report_path)]) == 1
    report = json.loads(report_path.read_text('utf-8'))
    assert report['ok'] is False
    assert 'missing bundled dependency' in report['error']


def _report_process(monkeypatch, report, *, returncode=0):
    def run(command, **kwargs):
        assert '--report-file' in command
        path = Path(command[command.index('--report-file') + 1])
        assert kwargs['env']['QT_QPA_PLATFORM'] == 'offscreen'
        assert kwargs['cwd'] != str(REPO_ROOT)
        if report is not None:
            path.write_text(json.dumps(report), encoding='utf-8')
        return subprocess.CompletedProcess(command, returncode, stdout=None, stderr=None)

    monkeypatch.setattr(packaging.subprocess, 'run', run)


def _frozen_report(runtime_report):
    assert isinstance(runtime_report, dict)
    # Match JSON transport (preview histogram keys become strings).
    report = json.loads(json.dumps(runtime_report))
    report['frozen'] = True
    return report


def test_smoke_test_reads_explicit_report_with_no_stdout(monkeypatch, tmp_path, runtime_report):
    report = _frozen_report(runtime_report)
    _report_process(monkeypatch, report)
    assert packaging.smoke_test(tmp_path / 'bundle.exe') == report


@pytest.mark.parametrize('changes', [
    {'pack_bundled': True}, {'window_shown': False}, {'events_processed': False},
    {'approval_refused': False}, {'classification_attempted': False},
    {'classification_output_created': True}, {'review_codes': 1},
    {'approved_codes': {'JP': 'JP'}}, {'version': 'wrong'}, {'rules_version': ''},
    {'frozen': False}, {'schema_version': 2}, {'ok': False},
    {'preview': {'total_records': 0}}, {'xlsx_preview': {'total_records': 0}},
    {'rules_version': 'stale-but-nonempty'},
    {'bundled_pack_paths': ['hidden.sqlite']},
    {'classification_error': 'unrelated failure'},
    {'assertion_failures': ['window_shown']},
])
def test_smoke_test_validates_each_claim(monkeypatch, tmp_path, runtime_report, changes):
    report = _frozen_report(runtime_report)
    report.update(changes)
    _report_process(monkeypatch, report)
    with pytest.raises(SystemExit, match='self.test'):
        packaging.smoke_test(tmp_path / 'bundle.exe')


@pytest.mark.parametrize('report', [None, {}, [], {'ok': True}])
def test_smoke_test_rejects_missing_or_incomplete_reports(monkeypatch, tmp_path, report):
    _report_process(monkeypatch, report)
    with pytest.raises(SystemExit, match='self.test'):
        packaging.smoke_test(tmp_path / 'bundle.exe')


def test_smoke_test_handles_timeout(monkeypatch, tmp_path):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs['timeout'], output=b'partial')

    monkeypatch.setattr(packaging.subprocess, 'run', timeout)
    with pytest.raises(SystemExit, match='timed out'):
        packaging.smoke_test(tmp_path / 'bundle.exe')


@pytest.mark.parametrize('failure', ['timeout', 'invalid-report'])
def test_cleanup_of_a_locked_windows_file_preserves_primary_failure(monkeypatch, tmp_path, failure):
    real_temporary_directory = packaging.tempfile.TemporaryDirectory

    class LockedTemporaryDirectory(real_temporary_directory):
        @classmethod
        def _rmtree(cls, name, ignore_errors=False, repeated=False):
            if not ignore_errors:
                raise PermissionError('onefile child still holds the extraction directory')
            return super()._rmtree(name, ignore_errors=ignore_errors, repeated=repeated)

    def run(command, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, kwargs['timeout'])
        return subprocess.CompletedProcess(command, 0, stdout=None, stderr=None)

    monkeypatch.setattr(packaging.tempfile, 'TemporaryDirectory', LockedTemporaryDirectory)
    monkeypatch.setattr(packaging.subprocess, 'run', run)
    message = 'timed out' if failure == 'timeout' else 'report is missing or invalid'
    with pytest.raises(SystemExit, match=message):
        packaging.smoke_test(tmp_path / 'bundle.exe')


@pytest.mark.skipif(os.name != 'nt' or os.environ.get('WASE_RUN_PACKAGING_TESTS') != '1',
                    reason='real Windows build: set WASE_RUN_PACKAGING_TESTS=1')
def test_the_packaged_executable_passes_its_own_self_test(tmp_path):
    executable = packaging.build(tmp_path, onefile=True)
    report = packaging.smoke_test(executable)
    assert report['ok'] is True
    assert report['frozen'] is True
