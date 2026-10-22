"""The GUI review panel may only assert codes the signed approval ratifies."""

import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6')

from world_address_engine.gui.review_store import ReviewError, ReviewStore  # noqa: E402
from tests.unit.test_classify import hkp  # noqa: E402


@pytest.fixture(scope='session')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_gui_review_panel_offers_only_approved_codes(tmp_path, app):
    """A code the signed approval does not ratify can never be asserted."""
    from world_address_engine.gui.app import MainWindow
    from world_address_engine.hkp.approval import sign_manifest
    from tests.hkp_master_fixture import FIXTURE_KEY

    master = hkp(tmp_path)
    payload = json.loads(master.manifest_path.read_text(encoding='utf-8'))
    payload.pop('signature')
    payload['approved_destinations'] = ['india']
    restricted = tmp_path / 'restricted.approval.json'
    restricted.write_text(json.dumps(sign_manifest(payload, FIXTURE_KEY),
                                     ensure_ascii=False, indent=2), encoding='utf-8')
    window = MainWindow()
    window.hkp_db.setText(str(master.db_path))
    window.approval_manifest.setText(str(restricted))
    window.approval_key.setText(str(master.key_path))
    window._load_approved_codes()
    assert window.approved_codes == {'india': 'IN'}
    assert [window.review_code.itemText(i)
            for i in range(window.review_code.count())] == ['IN']
    store = ReviewStore(tmp_path / 'review.jsonl', operator='Ada Lovelace')
    with pytest.raises(ReviewError):
        store.decide(1, new_code='US', reason='because',
                     approved_codes=window.approved_codes)
    window.close()


def test_gui_without_an_approval_offers_no_review_codes(tmp_path, app):
    """Without a signed approval the operator cannot assert any code."""
    from world_address_engine.gui.app import MainWindow

    master = hkp(tmp_path)
    window = MainWindow()
    window.hkp_db.setText(str(master.db_path))
    window._load_approved_codes()
    assert window.approved_codes == {}
    assert window.review_code.count() == 0
    window.close()
