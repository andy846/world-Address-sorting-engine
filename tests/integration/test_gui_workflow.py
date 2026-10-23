"""The offline desktop workflow: import, classify, review, export.

The tests run headless with the offscreen Qt platform plugin.
"""

import csv
import json
import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6')

from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from world_address_engine.gui.review_store import ReviewError, ReviewStore  # noqa: E402
from tests.unit.test_classify import hkp  # noqa: E402
from tests.unit.test_retrieve import geo  # noqa: E402


@pytest.fixture(scope='session')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def _source(path: Path, addresses):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2', 'Control no'])
        for index, address in enumerate(addresses, 1):
            writer.writerow(['Recipient', address, f'{index:06d}'])


def _read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def _wait_for_job(window, app, timeout=120.0):
    """Wait for the worker thread to report back through the event loop."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if window.job_state in ('done', 'failed'):
            app.processEvents()
            return window.job_state
        time.sleep(0.01)
    return window.job_state


def _wait_for_idle(window, app, timeout=60.0):
    """Wait until no worker thread is running any more."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if not window.busy:
            app.processEvents()
            return True
        time.sleep(0.01)
    return False


def _prepare(window, data, master, geo_db):
    window.input_path.setText(str(data))
    window.geo_db.setText(str(geo_db))
    window.hkp_db.setText(str(master.db_path))
    window.approval_manifest.setText(str(master.manifest_path))
    window.approval_key.setText(str(master.key_path))
    window.test_only.setChecked(True)
    window._load_columns(data)
    window.address_columns.item(1).setSelected(True)


def test_review_decision_is_audited(tmp_path):
    store = ReviewStore(tmp_path / 'review.jsonl', operator='  Ada Lovelace ',
                        catalogue_version='fixture-2026-10',
                        geo_pack_versions='geonames-test',
                        rules_version='2026-10-23.3',
                        approval_id='fixture-approval',
                        approval_manifest_sha256='a' * 64)
    decision = store.decide(7, record_id='000007', original_status='REVIEW_AMBIGUOUS',
                            original_reason='MULTIPLE_PLAUSIBLE_GEOGRAPHIC_DESTINATIONS',
                            new_code='JP', reason='operator confirmed the prefecture',
                            approved_codes={'japan': 'JP'})
    assert decision.operator == 'Ada Lovelace'
    assert decision.new_code == 'JP'
    assert decision.decided_at
    assert decision.catalogue_version == 'fixture-2026-10'
    assert decision.geo_pack_versions == 'geonames-test'
    assert decision.rules_version == '2026-10-23.3'
    assert decision.approval_id == 'fixture-approval'
    assert decision.approval_manifest_sha256 == 'a' * 64
    again = ReviewStore(tmp_path / 'review.jsonl', operator='Ada Lovelace')
    assert again.decisions() == (decision,)
    log = store.write_csv(tmp_path / 'Review_Corrections.csv')
    rows = _read(log)
    assert rows[0]['Operator'] == 'Ada Lovelace'
    assert rows[0]['New_Code'] == 'JP'
    assert rows[0]['Reason'] == 'operator confirmed the prefecture'
    assert rows[0]['Rules_Version'] == '2026-10-23.3'
    assert rows[0]['Approval_ID'] == 'fixture-approval'


def test_review_requires_an_operator_reason_and_an_approved_code(tmp_path):
    store = ReviewStore(tmp_path / 'review.jsonl', operator='')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='JP', reason='because')
    store = ReviewStore(tmp_path / 'review.jsonl', operator='Ada')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='JP', reason='  ')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='ZZ', reason='because', approved_codes={'japan': 'JP'})


def test_review_rejects_a_non_positive_record_number(tmp_path):
    """A decision must name a real source record."""
    store = ReviewStore(tmp_path / 'review.jsonl', operator='Ada')
    with pytest.raises(ReviewError):
        store.decide(0, reason='because')
    with pytest.raises(ReviewError):
        store.decide(-3, reason='because')


def test_gui_import_map_classify_export(tmp_path, app):
    from world_address_engine.gui.app import MainWindow

    data = tmp_path / 'sample.csv'
    _source(data, ['Mumbai, India', 'Tokyo, Japan', 'Springfield'])
    master = hkp(tmp_path)
    window = MainWindow()
    _prepare(window, data, master, geo(tmp_path))
    window.start_job()
    assert _wait_for_job(window, app) == 'done'
    assert window.counts.rowCount() == 2, 'India and Japan should be counted'
    codes = {window.counts.item(row, 0).text(): window.counts.item(row, 1).text()
             for row in range(window.counts.rowCount())}
    assert codes == {'IN': '1', 'JP': '1'}
    assert window.review_table.rowCount() == 1
    manifest = json.loads((window._output_dir / 'Run_Manifest.json').read_text(encoding='utf-8'))
    assert manifest['data_class'] == 'TEST_ONLY_UNVERIFIED'
    assert 'TEST_ONLY_UNVERIFIED' in (window._output_dir / 'DATA_CLASS.txt').read_text(encoding='utf-8')
    window.close()


def test_gui_shows_unsupported_language_for_review(tmp_path, app):
    from world_address_engine.gui.app import MainWindow

    data = tmp_path / 'sample.csv'
    _source(data, ['Москва, Россия'])
    master = hkp(tmp_path)
    window = MainWindow()
    _prepare(window, data, master, geo(tmp_path))
    window.start_job()
    assert _wait_for_job(window, app) == 'done'
    assert window.review_table.rowCount() == 1
    reason = window.review_table.item(0, 3).text()
    assert 'UNSUPPORTED_LANGUAGE' in reason
    window.close()


def test_review_override_changes_one_record_only(tmp_path, app):
    from world_address_engine.gui.app import MainWindow

    data = tmp_path / 'sample.csv'
    _source(data, ['Springfield', 'Springfield', 'Mumbai, India'])
    master = hkp(tmp_path)
    window = MainWindow()
    _prepare(window, data, master, geo(tmp_path))
    window.start_job()
    assert _wait_for_job(window, app) == 'done'
    assert window.review_table.rowCount() == 2
    window.operator.setText('Ada Lovelace')
    window.review_reason.setText('confirmed with the customer')
    window.review_code.setCurrentText('US')
    window.review_table.selectRow(0)
    window.apply_review()
    window.export_reviews()
    assert _wait_for_idle(window, app)
    rows = _read(window._output_dir / 'Classified_Addresses.csv')
    assert len(rows) == 3
    assert rows[0]['HKP_Destination_Code'] == 'US'
    assert rows[0]['Match_Method'] == 'MANUAL_REVIEW'
    assert rows[1]['HKP_Destination_Code'] == ''
    assert rows[2]['HKP_Destination_Code'] == 'IN'
    summary = _read(window._output_dir / 'Country_Summary.csv')
    assert {r['HKP_Destination_Code']: r['Count'] for r in summary} == {'US': '1', 'IN': '1'}
    corrections = _read(window._output_dir / 'Review_Corrections.csv')
    assert len(corrections) == 1
    assert corrections[0]['Operator'] == 'Ada Lovelace'
    window.close()


def test_the_worker_really_runs_off_the_gui_thread(tmp_path, app):
    """The classification runs on a worker thread, not on the GUI thread."""
    from world_address_engine.gui.app import MainWindow

    data = tmp_path / 'sample.csv'
    _source(data, ['Mumbai, India'])
    master = hkp(tmp_path)
    window = MainWindow()
    _prepare(window, data, master, geo(tmp_path))
    gui_ident = threading.get_ident()
    window.start_job()
    assert window.worker_thread is not None
    assert window.worker_thread is not threading.current_thread()
    assert _wait_for_job(window, app) == 'done'
    # The worker recorded the OS thread it really ran on. It must not be
    # the thread that owns the window.
    assert window.worker_thread_ident is not None
    assert window.worker_thread_ident != gui_ident
    assert window.counts.rowCount() == 1, 'the job really produced a result'
    window.close()


def test_closing_while_a_worker_runs_is_refused(tmp_path, app, monkeypatch):
    """A running worker is never destroyed together with the window.

    Destroying a running QThread aborts the interpreter (0xC0000409), so
    the close is refused until the worker has really stopped.
    """
    from world_address_engine.gui import app as gui_app
    from world_address_engine.gui.app import MainWindow

    monkeypatch.setattr(gui_app, 'CLOSE_GRACE_SECONDS', 0.2)
    window = MainWindow()

    def slow(_emit):
        time.sleep(1.0)
        return {'run_status': 'COMPLETE'}

    assert window._start_worker(slow) is True
    assert window.busy
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted(), 'the close must be refused while a worker runs'
    deadline = time.monotonic() + 10.0
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not window.busy
    window.close()


def test_the_review_panel_reports_how_many_rows_it_hides(tmp_path, app):
    """A truncated review table must say how many rows are missing."""
    from world_address_engine.gui import app as gui_app
    from world_address_engine.gui.app import MainWindow

    monkeypatch = getattr(gui_app, 'MAX_REVIEW_ROWS', 5000)
    original = gui_app.MAX_REVIEW_ROWS
    gui_app.MAX_REVIEW_ROWS = 1
    try:
        data = tmp_path / 'sample.csv'
        _source(data, ['Springfield', 'Springfield', 'Springfield'])
        master = hkp(tmp_path)
        window = MainWindow()
        _prepare(window, data, master, geo(tmp_path))
        window.start_job()
        assert _wait_for_job(window, app) == 'done'
        assert window.review_table.rowCount() == 1
        assert '3 records need review' in window.review_summary.text()
        assert 'first 1' in window.review_summary.text()
        window.close()
    finally:
        gui_app.MAX_REVIEW_ROWS = original


def test_the_column_reader_honours_the_selected_encoding(tmp_path, app):
    """The header is read with the encoding the operator selected."""
    from world_address_engine.gui.app import MainWindow

    data = tmp_path / 'big5.csv'
    with data.open('w', encoding='big5', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2'])
        writer.writerow(['收件人', '台北市'])
    window = MainWindow()
    window.encoding.setCurrentText('big5')
    window._load_columns(data)
    labels = [window.address_columns.item(i).text()
              for i in range(window.address_columns.count())]
    assert labels == ['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2']
    window.close()


def test_completed_worker_does_not_keep_a_closed_window_alive(app):
    """A later worker must not collect an earlier window's callback cycle."""
    import gc
    import weakref

    from world_address_engine.gui.app import MainWindow

    collecting = gc.isenabled()
    gc.disable()
    try:
        window = MainWindow()
        assert window._start_worker(
            lambda _emit: 1,
            on_success=window._on_progress,
            on_error=window._on_background_error,
            on_finished=window._load_approved_codes,
        )
        assert _wait_for_idle(window, app)
        app.processEvents()
        window.close()
        reference = weakref.ref(window)
        del window
        app.processEvents()
        assert reference() is None, 'completed callbacks retain the closed window'
    finally:
        # Qt wrappers must be reclaimed on their owning GUI thread.
        gc.collect()
        if collecting:
            gc.enable()
