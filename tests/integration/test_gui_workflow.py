"""The offline desktop workflow: import, classify, review, export.

The tests run headless with the offscreen Qt platform plugin.
"""

import csv
import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6')

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
                        geo_pack_versions='geonames-test')
    decision = store.decide(7, record_id='000007', original_status='REVIEW_AMBIGUOUS',
                            original_reason='MULTIPLE_PLAUSIBLE_GEOGRAPHIC_DESTINATIONS',
                            new_code='JP', reason='operator confirmed the prefecture',
                            approved_codes={'japan': 'JP'})
    assert decision.operator == 'Ada Lovelace'
    assert decision.new_code == 'JP'
    assert decision.decided_at
    assert decision.catalogue_version == 'fixture-2026-10'
    assert decision.geo_pack_versions == 'geonames-test'
    again = ReviewStore(tmp_path / 'review.jsonl', operator='Ada Lovelace')
    assert again.decisions() == (decision,)
    log = store.write_csv(tmp_path / 'Review_Corrections.csv')
    rows = _read(log)
    assert rows[0]['Operator'] == 'Ada Lovelace'
    assert rows[0]['New_Code'] == 'JP'
    assert rows[0]['Reason'] == 'operator confirmed the prefecture'


def test_review_requires_an_operator_reason_and_an_approved_code(tmp_path):
    store = ReviewStore(tmp_path / 'review.jsonl', operator='')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='JP', reason='because')
    store = ReviewStore(tmp_path / 'review.jsonl', operator='Ada')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='JP', reason='  ')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='ZZ', reason='because', approved_codes={'japan': 'JP'})


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


def test_gui_runs_the_job_off_the_main_thread(tmp_path, app):
    """The classification runs on a worker thread, not on the GUI thread."""
    from PySide6.QtCore import QThread
    from world_address_engine.gui.app import MainWindow

    data = tmp_path / 'sample.csv'
    _source(data, ['Mumbai, India'])
    master = hkp(tmp_path)
    window = MainWindow()
    _prepare(window, data, master, geo(tmp_path))
    window.start_job()
    assert window.worker_thread is not None
    assert window.worker_thread is not QThread.currentThread()
    assert _wait_for_job(window, app) == 'done'
    window.close()
