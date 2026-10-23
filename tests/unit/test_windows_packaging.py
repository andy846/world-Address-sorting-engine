"""Packaging checks exercise reports and archives without building a real bundle."""

import builtins
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'tools'))

import gui_entry_point as entry  # noqa: E402
import package_windows as packaging  # noqa: E402


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


def test_bundle_proves_icon_progress_and_completed_pending_case_view(runtime_report):
    feedback = runtime_report['gui_feedback']
    assert feedback == {'icon_loaded': True, 'stage_events_observed': True,
                        'address_line_order_preserved': True,
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
