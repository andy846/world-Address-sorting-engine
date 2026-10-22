"""The GUI review panel may only assert codes the signed approval ratifies."""

import json
import os
import time

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6')

from world_address_engine.gui.review_store import ReviewError, ReviewStore  # noqa: E402
from tests.unit.test_classify import hkp  # noqa: E402
from tests.unit.test_retrieve import geo  # noqa: E402


@pytest.fixture(scope='session')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _restricted_approval(master, tmp_path, destinations):
    """A signed approval that ratifies only some destinations."""
    from world_address_engine.hkp.approval import sign_manifest
    from tests.hkp_master_fixture import FIXTURE_KEY

    payload = json.loads(master.manifest_path.read_text(encoding='utf-8'))
    payload.pop('signature')
    payload['approved_destinations'] = list(destinations)
    path = tmp_path / 'restricted.approval.json'
    path.write_text(json.dumps(sign_manifest(payload, FIXTURE_KEY),
                               ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def _source(path, addresses):
    import csv
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2'])
        for address in addresses:
            writer.writerow(['Recipient', address])


def _wait(window, app, timeout=120.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if window.job_state in ('done', 'failed'):
            app.processEvents()
            return window.job_state
        time.sleep(0.01)
    return window.job_state


def test_gui_review_panel_offers_only_the_codes_the_run_approved(tmp_path, app):
    """A code the signed approval does not ratify can never be asserted."""
    from world_address_engine.gui.app import MainWindow

    master = hkp(tmp_path)
    restricted = _restricted_approval(master, tmp_path, ['india'])
    data = tmp_path / 'sample.csv'
    _source(data, ['Mumbai, India', 'Tokyo, Japan'])
    window = MainWindow()
    window.input_path.setText(str(data))
    window.geo_db.setText(str(geo(tmp_path)))
    window.hkp_db.setText(str(master.db_path))
    window.approval_manifest.setText(str(restricted))
    window.approval_key.setText(str(master.key_path))
    window.test_only.setChecked(True)
    window._load_columns(data)
    window.address_columns.item(1).setSelected(True)
    window.start_job()
    assert _wait(window, app) == 'done'
    assert window.approved_codes == {'india': 'IN'}
    assert [window.review_code.itemText(i)
            for i in range(window.review_code.count())] == ['IN']
    store = ReviewStore(tmp_path / 'review.jsonl', operator='Ada Lovelace')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='US', reason='because',
                     approved_codes=window.approved_codes)
    window.close()


def test_the_review_panel_follows_the_run_not_the_operator_text_boxes(tmp_path, app):
    """Pointing the approval box at another manifest must not widen the panel.

    The panel is bound to the approval that authorised the run, so the
    operator cannot swap in a wider approval after the fact.
    """
    from world_address_engine.gui.app import MainWindow

    master = hkp(tmp_path)
    restricted = _restricted_approval(master, tmp_path, ['india'])
    data = tmp_path / 'sample.csv'
    _source(data, ['Mumbai, India'])
    window = MainWindow()
    window.input_path.setText(str(data))
    window.geo_db.setText(str(geo(tmp_path)))
    window.hkp_db.setText(str(master.db_path))
    window.approval_manifest.setText(str(restricted))
    window.approval_key.setText(str(master.key_path))
    window.test_only.setChecked(True)
    window._load_columns(data)
    window.address_columns.item(1).setSelected(True)
    window.start_job()
    assert _wait(window, app) == 'done'
    assert window.approved_codes == {'india': 'IN'}
    # The operator now points the box at the unrestricted approval.
    window.approval_manifest.setText(str(master.manifest_path))
    window._load_approved_codes()
    assert window.approved_codes == {'india': 'IN'}, (
        'the panel must stay bound to the approval that authorised the run')
    window.close()


def test_gui_without_a_run_offers_no_review_codes(tmp_path, app):
    """Without a finished run the operator cannot assert any code."""
    from world_address_engine.gui.app import MainWindow

    master = hkp(tmp_path)
    window = MainWindow()
    window.hkp_db.setText(str(master.db_path))
    window.approval_manifest.setText(str(master.manifest_path))
    window.approval_key.setText(str(master.key_path))
    window._load_approved_codes()
    assert window.approved_codes == {}
    assert window.review_code.count() == 0
    window.close()

