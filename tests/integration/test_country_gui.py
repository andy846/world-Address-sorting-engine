"""Synthetic country GUI contracts; no customer files or installed packs."""

import importlib
import json
import os
import re
import sys
import threading
import time
import types

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        time.sleep(0.005)
    assert predicate(), 'GUI did not reach the expected state'


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module('world_address_engine.gui.country_app')
    instance = module.CountryAnalysisWindow()
    yield instance
    instance.cancel_job()
    wait(app, lambda: not instance.busy)
    instance.close()
    app.processEvents()


def source(tmp_path):
    path = tmp_path / 'synthetic.csv'
    path.write_text('NAME_ADDRESS_LINE1,Other\nTokyo Japan,001\n', encoding='utf-8')
    return path


def configure(window, tmp_path):
    window.input_path.setText(str(source(tmp_path)))
    pack = tmp_path / 'synthetic.db'
    pack.touch()
    window.geo_db.setText(str(pack))
    window.output_dir.setText(str(tmp_path / 'export'))
    window.address_columns.addItem('NAME_ADDRESS_LINE1')
    window.address_columns.item(0).setSelected(True)


def report(state='COMPLETE'):
    return {'job_kind': 'country-analysis', 'state': state, 'total_records': 6,
            'status_counts': {'DETERMINED': 3, 'INFERRED': 2, 'UNRESOLVED': 1},
            'destination_counts': {'JP': 5},
            'run_metadata': {'catalogue_version': 'synthetic-v1'}}


def install_runner(monkeypatch, analyze, resume=None):
    # Other agents own this module. Its public boundary can be tested before it lands.
    module = types.ModuleType('world_address_engine.jobs.country_analysis')
    module.analyze_job = analyze
    module.resume_analysis = resume or (lambda *a, **kw: report())
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_normal_window_has_country_inputs_and_no_postal_approval(window):
    assert 'Country' in window.windowTitle()
    for name in ('input_path', 'output_dir', 'encoding', 'sheet_name',
                 'address_columns', 'geo_db', 'preview_button', 'resume_button'):
        assert getattr(window, name) is not None
    labels = ' '.join(widget.text() for kind in (QLabel, QPushButton)
                      for widget in window.findChildren(kind))
    assert not re.search(r'\b(hkp|approval|air|surface|zone|novsn)\b', labels.lower())
    assert [window.counts.horizontalHeaderItem(i).text() for i in range(3)] == [
        'Country Code', 'Country name', 'Count']
    assert not window.cancel_button.isEnabled()


@pytest.mark.parametrize('extended,compact,expected', [
    (True, True, 'geonames-extended-global-2026-10-22-k2'),
    (False, True, 'geonames-compact-global-2026-10-22-k2'),
    (False, False, None),
])
def test_pack_discovery_prefers_available_k2(tmp_path, monkeypatch, app,
                                           extended, compact, expected):
    monkeypatch.chdir(tmp_path)
    for profile, present in [('extended', extended), ('compact', compact)]:
        if present:
            folder = tmp_path / 'packs' / f'geonames-{profile}-global-2026-10-22-k2'
            folder.mkdir(parents=True)
            (folder / 'pack.db').touch()
    legacy = tmp_path / 'packs' / 'geonames-extended-global-2026-10-22'
    legacy.mkdir(parents=True)
    (legacy / 'pack.db').touch()
    from world_address_engine.gui.country_app import CountryAnalysisWindow
    instance = CountryAnalysisWindow()
    try:
        chosen = instance.geo_db.text()
        assert chosen == (str(tmp_path / 'packs' / expected / 'pack.db') if expected else '')
    finally:
        instance.close()


def test_analyze_passes_normal_inputs_reads_exports_and_updates_country_counts(
        window, tmp_path, app, monkeypatch):
    configure(window, tmp_path)
    window.encoding.setCurrentText('big5')
    window.sheet_name.setText('Addresses')
    gui_ident = threading.get_ident()
    threads = []
    from world_address_engine.gui import country_app
    original_read = country_app._read_country_export

    def read(*args):
        threads.append(threading.get_ident())
        return original_read(*args)

    monkeypatch.setattr(country_app, '_read_country_export', read)

    def analyze(input_path, output_dir, geo_db, input_options=None, *,
                catalogue_path=None, batch_size=1000, max_batches=None,
                on_progress=None, cancel_requested=None, keep_checkpoint=False):
        assert threading.get_ident() != gui_ident
        assert input_path == tmp_path / 'synthetic.csv'
        assert geo_db == tmp_path / 'synthetic.db'
        assert input_options == {'encoding': 'big5', 'sheet_name': 'Addresses',
                                 'address_columns': ['NAME_ADDRESS_LINE1']}
        assert catalogue_path is None
        assert callable(cancel_requested)
        on_progress(6)
        output_dir.mkdir()
        (output_dir / 'Run_Manifest.json').write_text(json.dumps(report()), encoding='utf-8')
        (output_dir / 'Country_Summary.csv').write_text(
            'Country_Code,Country_Name,Count\nJP,Japan,5\n', encoding='utf-8-sig')
        return report()

    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, lambda: window.job_state in ('done', 'failed') and not window.busy)
    assert window.job_state == 'done', window.log.toPlainText()
    assert threads and all(ident != gui_ident for ident in threads)
    assert window.counts.rowCount() == 1
    assert [window.counts.item(0, i).text() for i in range(3)] == ['JP', 'Japan', '5']
    summary = window.summary.text().lower()
    for text in ('determined: 3', 'inferred: 2', 'unresolved: 1', 'total: 6'):
        assert text in summary
    assert 'invalid input' not in summary
    assert str(tmp_path / 'export') in window.export_location.text()
    assert window.open_output_button.isEnabled()
    assert window.progress.value() == window.progress.maximum()


def test_preview_runs_cli_scan_and_header_read_off_thread(window, tmp_path, app, monkeypatch):
    from world_address_engine import cli
    path = source(tmp_path)
    gui_ident = threading.get_ident()
    actual_preview = cli.preview
    calls = []

    def preview(*args, **kwargs):
        calls.append(threading.get_ident())
        return actual_preview(*args, **kwargs)

    monkeypatch.setattr(cli, 'preview', preview)
    real_open = type(path).open
    reads = []

    def track_read(self, *args, **kwargs):
        if self == path:
            reads.append(threading.get_ident())
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(type(path), 'open', track_read)
    window.input_path.setText(str(path))
    window.preview_button.click()
    wait(app, lambda: not window.busy)
    assert calls and all(ident != gui_ident for ident in calls + reads)
    assert [window.address_columns.item(i).text()
            for i in range(window.address_columns.count())] == ['NAME_ADDRESS_LINE1', 'Other']
    assert [item.text() for item in window.address_columns.selectedItems()] == ['NAME_ADDRESS_LINE1']
    assert '1' in window.preview_summary.text()
    assert 'Tokyo' not in window.log.toPlainText()


def test_custom_columns_can_be_discovered_before_preview_mapping(window, tmp_path, app):
    path = tmp_path / 'custom.csv'
    path.write_text('Address,ID\nTokyo Japan,001\n', encoding='utf-8')
    window.input_path.setText(str(path))
    window.preview_button.click()
    wait(app, lambda: not window.busy)
    assert window.address_columns.item(0).text() == 'Address'
    window.address_columns.item(0).setSelected(True)
    window.preview_button.click()
    wait(app, lambda: not window.busy)
    assert '1' in window.preview_summary.text()


def test_preview_honours_xlsx_worksheet(window, tmp_path, app):
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = 'Ignore'
    sheet = book.create_sheet('Addresses')
    sheet.append(['Address', 'ID'])
    sheet.append(['Japan', '0001'])
    path = tmp_path / 'synthetic.xlsx'
    book.save(path)
    book.close()
    window.input_path.setText(str(path))
    window.sheet_name.setText('Addresses')
    window.preview_button.click()
    wait(app, lambda: not window.busy)
    assert window.address_columns.item(0).text() == 'Address'
    window.address_columns.item(0).setSelected(True)
    window.preview_button.click()
    wait(app, lambda: not window.busy)
    assert '1' in window.preview_summary.text()


def test_preview_honours_selected_encoding(window, tmp_path, app):
    path = tmp_path / 'synthetic-big5.csv'
    path.write_text('NAME_ADDRESS_LINE1,\u7de8\u865f\n\u65e5\u672c,001\n', encoding='big5')
    window.input_path.setText(str(path))
    window.encoding.setCurrentText('big5')
    window.preview_button.click()
    wait(app, lambda: not window.busy)
    assert window.address_columns.item(1).text() == '\u7de8\u865f'
    assert '0 records with decoding errors' in window.preview_summary.text()


def test_preview_cancel_stops_scan_and_closes_source(window, tmp_path, app, monkeypatch):
    from world_address_engine import cli
    from world_address_engine.io.delimited import iter_csv_records

    path = source(tmp_path)
    record = next(iter_csv_records(path, 'utf-8', ('NAME_ADDRESS_LINE1',)))
    started = threading.Event()
    closed = threading.Event()
    scanned = []

    def rows(*args, **kwargs):
        try:
            for index in range(10000):
                scanned.append(index)
                started.set()
                time.sleep(0.001)
                yield record
        finally:
            closed.set()

    monkeypatch.setattr(cli, 'iter_csv_records', rows)
    window.input_path.setText(str(path))
    window.preview_input()
    wait(app, started.is_set)
    window.cancel_job()
    wait(app, lambda: not window.busy, timeout=2)
    assert closed.is_set()
    assert len(scanned) < 10000
    assert 'cancelled' in window.preview_summary.text().lower()
    assert 'ready' not in window.statusBar().currentMessage().lower()


def test_reader_accepts_published_bilingual_summary_and_unresolved_row(window, tmp_path, app, monkeypatch):
    configure(window, tmp_path)

    def analyze(input_path, output_dir, geo_db, input_options, **kwargs):
        output_dir.mkdir()
        manifest = report()
        manifest['run_status'] = manifest.pop('state')
        (output_dir / 'Run_Manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (output_dir / 'Country_Summary.csv').write_text(
            'Country_Code,Country_Name_TC,Country_Name_EN,Count,Percentage\n'
            'JP,\u65e5\u672c,Japan,5,83.33\n,,,1,16.67\n', encoding='utf-8-sig')
        return manifest

    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'done', window.log.toPlainText()
    assert window.counts.rowCount() == 2
    assert 'Japan' in window.counts.item(0, 1).text()
    assert window.counts.item(1, 0).text() == ''
    assert window.counts.item(1, 1).text() == 'Unresolved'
    assert window.counts.item(1, 2).text() == '1'


def test_changing_input_discards_stale_column_mapping(window, tmp_path, app):
    configure(window, tmp_path)
    other = tmp_path / 'other.csv'
    other.write_text('Address,ID\nJapan,001\n', encoding='utf-8')
    window.input_path.setText(str(other))
    window.preview_button.click()
    wait(app, lambda: not window.busy)
    assert window.address_columns.item(0).text() == 'Address'
    assert window.job_state != 'failed'


def test_completed_worker_does_not_retain_closed_window(app, monkeypatch, tmp_path):
    import gc
    import weakref
    from world_address_engine.gui.country_app import CountryAnalysisWindow

    monkeypatch.chdir(tmp_path)
    collecting = gc.isenabled()
    gc.disable()
    try:
        instance = CountryAnalysisWindow()
        instance._start_worker(lambda emit: 1, on_success=instance._on_progress)
        wait(app, lambda: not instance.busy)
        instance.close()
        reference = weakref.ref(instance)
        del instance
        app.processEvents()
        assert reference() is None
    finally:
        gc.collect()
        if collecting:
            gc.enable()


def test_cancel_is_resumable_and_resume_uses_output_folder(window, tmp_path, app, monkeypatch):
    configure(window, tmp_path)
    started = threading.Event()

    def analyze(*args, on_progress, cancel_requested, **kwargs):
        started.set()
        while not cancel_requested():
            time.sleep(0.005)
        on_progress(6)
        return report('CANCELLED')

    def resume(output_dir, *, max_batches=None, on_progress=None,
               cancel_requested=None, keep_checkpoint=False):
        assert output_dir == tmp_path / 'export'
        assert threading.get_ident() != gui_ident
        return report()

    gui_ident = threading.get_ident()
    install_runner(monkeypatch, analyze, resume)
    window.start_job()
    wait(app, started.is_set)
    window.cancel_button.click()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'cancelled'
    assert window.resume_button.isEnabled()
    assert 'resum' in window.statusBar().currentMessage().lower()
    window.resume_button.click()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'done'


def test_resume_works_in_fresh_window_without_source_or_pack(window, tmp_path, app, monkeypatch):
    output = tmp_path / 'paused'
    output.mkdir()
    window.output_dir.setText(str(output))

    def resume(output_dir, **kwargs):
        assert output_dir == output
        return report('PAUSED')

    install_runner(monkeypatch, lambda *a, **kw: pytest.fail('must resume'), resume)
    window.resume_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'paused'
    assert window.run_button.isEnabled() and window.resume_button.isEnabled()


def test_partial_runner_result_does_not_present_missing_breakdown_as_zero(
        window, tmp_path, app, monkeypatch):
    window.output_dir.setText(str(tmp_path / 'paused'))

    def resume(output_dir, **kwargs):
        return {'job_kind': 'country-analysis', 'run_status': 'PAUSED',
                'committed_records': 25}

    install_runner(monkeypatch, lambda *a, **kw: None, resume)
    window.resume_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'paused'
    assert 'Total: 25' in window.summary.text()
    assert 'Determined: pending' in window.summary.text()
    assert 'Inferred: pending' in window.summary.text()
    assert 'Unresolved: pending' in window.summary.text()


def test_runner_failure_restores_controls_and_releases_thread(window, tmp_path, app, monkeypatch):
    from world_address_engine.gui.app import _LIVE_THREADS
    configure(window, tmp_path)

    def fail(*args, **kwargs):
        raise ValueError('synthetic runner failure')

    install_runner(monkeypatch, fail)
    failures = []
    window.jobFailed.connect(failures.append)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed'
    assert failures == ['ValueError: synthetic runner failure']
    assert window.run_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert window.worker_thread not in _LIVE_THREADS


def test_close_cancels_without_blocking_or_destroying_running_thread(window, app):
    from world_address_engine.gui.app import _LIVE_THREADS
    release = threading.Event()

    def slow(_emit):
        release.wait(5)
        return None

    try:
        window.show()
        assert window._start_worker(slow)
        thread = window.worker_thread
        event = QCloseEvent()
        start = time.monotonic()
        window.closeEvent(event)
        assert time.monotonic() - start < 0.2
        assert not event.isAccepted()
        assert thread in _LIVE_THREADS
        assert window._cancel.is_set()
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        wait(app, lambda: bool(ticks))
    finally:
        release.set()
        wait(app, lambda: not window.busy)
    wait(app, lambda: not window.isVisible())
    assert thread not in _LIVE_THREADS


def test_busy_job_cannot_be_started_twice(window, tmp_path, app, monkeypatch):
    configure(window, tmp_path)
    release = threading.Event()
    calls = []

    def analyze(*args, **kwargs):
        calls.append(1)
        release.wait(5)
        return report()

    install_runner(monkeypatch, analyze)
    try:
        window.start_job()
        window.start_job()
        window.resume_job()
        assert window.busy and not window.run_button.isEnabled()
    finally:
        release.set()
        wait(app, lambda: not window.busy)
    assert calls == [1]


def test_main_opens_country_window_by_default(app, monkeypatch):
    from world_address_engine.gui import app as gui_app
    from world_address_engine.gui import country_app
    shown = []

    class FakeWindow:
        def show(self):
            shown.append('country')

    monkeypatch.setattr(country_app, 'CountryAnalysisWindow', FakeWindow)
    monkeypatch.setattr(QApplication, 'exec', lambda self: 17)
    monkeypatch.setattr('PySide6.QtWidgets.QApplication', lambda argv: app)
    assert gui_app.main([]) == 17
    assert shown == ['country']


def test_real_runner_publishes_country_table_and_pack_version(window, tmp_path, app):
    from tests.unit.test_retrieve import geo

    configure(window, tmp_path)
    window.geo_db.setText(str(geo(tmp_path)))
    (tmp_path / 'synthetic.csv').write_text(
        'NAME_ADDRESS_LINE1,ID\nJapan,001\nIndia,002\n,003\n', encoding='utf-8')
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'done', window.log.toPlainText()
    rows = [[window.counts.item(row, col).text() for col in range(3)]
            for row in range(window.counts.rowCount())]
    assert rows == [['IN', 'INDIA', '1'], ['JP', 'JAPAN', '1'], ['', 'Unresolved', '1']]
    assert 'Determined: 2' in window.summary.text()
    assert 'Unresolved: 1' in window.summary.text()
    assert 'GeoNames: sha256:' in window.source_versions.text()
    assert not (tmp_path / 'export' / '.country-state').exists()


def test_real_runner_cancel_callback_preserves_checkpoint_for_resume(
        window, tmp_path, app, monkeypatch):
    from tests.unit.test_retrieve import geo
    from world_address_engine.matching.country import CountryClassifier

    configure(window, tmp_path)
    window.geo_db.setText(str(geo(tmp_path)))
    entered = threading.Event()
    release = threading.Event()
    classify = CountryClassifier.classify

    def delayed(self, record):
        if not entered.is_set():
            entered.set()
            release.wait(5)
        return classify(self, record)

    monkeypatch.setattr(CountryClassifier, 'classify', delayed)
    try:
        window.start_job()
        wait(app, entered.is_set)
        window.cancel_button.click()
    finally:
        release.set()
        wait(app, lambda: not window.busy)
    assert window.job_state == 'cancelled', window.log.toPlainText()
    assert (tmp_path / 'export' / '.country-state' / 'config.json').is_file()
    assert not (tmp_path / 'export' / 'Run_Manifest.json').exists()
    window.resume_button.click()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'done', window.log.toPlainText()
    assert window.counts.item(0, 0).text() == 'JP'
    assert not (tmp_path / 'export' / '.country-state').exists()
