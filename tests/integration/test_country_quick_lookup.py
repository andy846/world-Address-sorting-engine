"""Public synthetic lookup contracts: no addresses printed or written."""
import threading
import time
from types import SimpleNamespace
import pytest
from tests.integration.test_country_gui import app, wait, window, reference_settings
from world_address_engine.gui import country_app as gui


def test_lookup_native_page_invalidation_and_worker_reuse(app, monkeypatch, tmp_path):
    worker_type = getattr(gui, 'LookupThread', None)
    assert worker_type is not None, 'Independent persistent lookup worker required'
    from world_address_engine.gui import country_lookup
    opened, closed, queried = [], [], []
    class Session:
        status = 'GeoNames: synthetic | Hong Kong: disabled | Zones: synthetic'
        def __init__(self, *args):
            opened.append(threading.get_ident())
        def lookup(self, text):
            queried.append(threading.get_ident())
            return {'code': 'JP', 'name': 'Japan', 'status': 'DETERMINED', 'zone': '3', 'novsn': 'F'}
        def close(self):
            closed.append(threading.get_ident())
    monkeypatch.setattr(country_lookup, 'LookupSession', Session)
    monkeypatch.setattr(gui, '_discover_geo_pack', lambda: str(tmp_path / 'pack.db'))
    monkeypatch.setattr(gui, '_discover_hk_pack', lambda: '')
    w = gui.CountryAnalysisWindow()
    try:
        assert [w.pages.tabText(i) for i in range(2)] == ['Batch analysis', 'Single address lookup']
        wait(app, lambda: w.quick.query.isEnabled())
        w.quick.address.setPlainText('Tokyo\nJapan')
        w.quick.query.click()
        wait(app, lambda: w.quick.copy.isEnabled())
        assert 'JP' in w.quick.result.text() and 'NOVSN: F' in w.quick.result.text()
        w.quick.address.setPlainText('Japan')
        assert not w.quick.copy.isEnabled() and not w.quick.result.text()
        w.quick.query.click()
        wait(app, lambda: w.quick.copy.isEnabled())
        assert len(opened) == 1 and len(queried) == 2
        assert set(opened + queried) == {opened[0]} and opened[0] != threading.get_ident()
        w.cancel_job()
        assert w.quick.query.isEnabled()
    finally:
        w.close()
        wait(app, lambda: not w._lookup_thread.isRunning())
    assert closed == opened


def test_lookup_edit_drops_late_result(app, monkeypatch, tmp_path):
    assert getattr(gui, 'LookupThread', None), 'Lookup generations required'
    from world_address_engine.gui import country_lookup
    entered, release = threading.Event(), threading.Event()
    class Session:
        status = 'Ready'
        def __init__(self, *args): pass
        def lookup(self, text):
            entered.set()
            release.wait(3)
            return {'code': 'JP', 'name': 'Japan', 'status': 'DETERMINED', 'zone': '3', 'novsn': 'F'}
        def close(self): pass
    monkeypatch.setattr(country_lookup, 'LookupSession', Session)
    monkeypatch.setattr(gui, '_discover_geo_pack', lambda: '')
    monkeypatch.setattr(gui, '_discover_hk_pack', lambda: '')
    w = gui.CountryAnalysisWindow()
    try:
        wait(app, lambda: w.quick.query.isEnabled())
        w.quick.address.setPlainText('Japan')
        w.quick.query.click()
        wait(app, entered.is_set)
        w.quick.address.setPlainText('Canada')
        release.set()
        wait(app, lambda: w.quick.query.isEnabled())
        assert not w.quick.copy.isEnabled() and not w.quick.result.text()
    finally:
        release.set()
        w.close()
        wait(app, lambda: not w._lookup_thread.isRunning())


def test_edit_during_initial_verification_still_becomes_ready(app, monkeypatch):
    from world_address_engine.gui import country_lookup
    entered, release = threading.Event(), threading.Event()
    class Session:
        status = 'Verified'
        def __init__(self, *args):
            entered.set()
            release.wait(3)
        def close(self): pass
    monkeypatch.setattr(country_lookup, 'LookupSession', Session)
    w = gui.CountryAnalysisWindow()
    try:
        wait(app, entered.is_set)
        w.quick.address.setPlainText('Japan')
        release.set()
        wait(app, lambda: w.quick.query.isEnabled(), timeout=1)
    finally:
        release.set()
        w.close()
        wait(app, lambda: not w._lookup_thread.isRunning())


def test_real_verified_lookup_reuses_model_and_rejects_corrupt_pack(tmp_path):
    import hashlib
    import json
    from tests.unit.test_retrieve import geo
    from world_address_engine.gui.country_lookup import LookupSession
    from world_address_engine.data.pack_registry import REQUIRED
    path = geo(tmp_path)
    manifest = dict.fromkeys(REQUIRED, '')
    manifest.update(pack_id='synthetic', pack_version='test', schema_version=1,
                    profile='EXTENDED_GLOBAL', record_count=20, source_sha256='0' * 64,
                    db_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    path.with_name('manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    session = LookupSession((str(path), ''))
    try:
        model = session.model
        assert not model._cache and model._cache_text_bytes == 0
        for address, code, zone, novsn in [('China', 'CN', 'CN - Airmail', 'F'),
                                          ('Hong Kong', 'HK', 'LOCAL', 'A'),
                                          ('Macau', 'MO', 'Macau - Surface', 'M')]:
            actual = session.lookup(address)
            assert (actual['code'], actual['zone'], actual['novsn']) == (code, zone, novsn)
            assert session.model is model
            assert not model._cache and model._cache_text_bytes == 0
    finally:
        session.close()
    manifest['db_sha256'] = '0' * 64
    path.with_name('manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError, match='checksum'):
        LookupSession((str(path), ''))


def test_query_during_batch_and_pack_settings_do_not_change_batch_pins(window, app, monkeypatch, tmp_path):
    from tests.integration.test_country_gui import configure, install_runner, report
    from world_address_engine.gui import country_lookup
    configure(window, tmp_path)
    entered = threading.Event()
    class Session:
        status = 'Verified synthetic'
        def __init__(self, *args): pass
        def lookup(self, text):
            return {'code': 'JP', 'name': 'Japan', 'status': 'DETERMINED', 'zone': '3', 'novsn': 'F'}
        def close(self): pass
    monkeypatch.setattr(country_lookup, 'LookupSession', Session)
    pinned = window.geo_db.text()
    def analyze(source, output, geo, options, cancel_requested, **kwargs):
        assert str(geo) == pinned
        entered.set()
        while not cancel_requested():
            time.sleep(.005)
        assert str(geo) == pinned
        return report('CANCELLED')
    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, entered.is_set)
    assert window.input_toggle.isEnabled(), 'Shared reference controls must stay reachable during batch'
    window.pages.setCurrentIndex(1)
    window.geo_db.setText('next-query-pack.db')
    wait(app, lambda: window.quick.query.isEnabled())
    window.quick.address.setPlainText('Japan')
    window.quick.query.click()
    wait(app, lambda: window.quick.copy.isEnabled())
    assert window.busy and window.job_state == 'running'
    window.cancel_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'cancelled' and window.quick.query.isEnabled()


def test_keyboard_newline_query_clear_and_copy(window, app, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from world_address_engine.gui import country_lookup
    class Session:
        status = 'Verified'
        def __init__(self, *args): pass
        def lookup(self, text):
            return {'code': 'JP', 'name': 'Japan', 'status': 'DETERMINED', 'zone': '3', 'novsn': 'F'}
        def close(self): pass
    monkeypatch.setattr(country_lookup, 'LookupSession', Session)
    window._pack_changed()
    window.pages.setCurrentIndex(1)
    window.show()
    wait(app, lambda: window.quick.query.isEnabled())
    window.quick.address.setFocus()
    QTest.keyClicks(window.quick.address, 'Tokyo')
    QTest.keyClick(window.quick.address, Qt.Key.Key_Return)
    QTest.keyClicks(window.quick.address, 'Japan')
    assert window.quick.address.toPlainText() == 'Tokyo\nJapan'
    QTest.keyClick(window.quick.address, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    wait(app, lambda: window.quick.copy.isEnabled())
    window.quick.copy.click()
    assert app.clipboard().text() == 'JP'
    window.quick.clear.click()
    assert not window.quick.copy.isEnabled() and not window.quick.result.text()
    assert window.quick.address.toPlainText() == ''



def test_large_font_quick_page_and_shared_settings_fit_viewport(window, app):
    from PySide6.QtGui import QFont, QFontDatabase
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    window.setFont(QFont('Segoe UI', 18))
    window.resize(960, 720)
    window.pages.setCurrentIndex(1)
    window.show()
    for _ in range(4):
        app.processEvents()
    assert window.width() == 960
    assert window.inputs.width() <= window.settings_scroll.viewport().width()
    for button in (window.quick.query, window.quick.clear, window.quick.copy):
        assert window.quick.rect().contains(button.geometry())


def test_close_waits_for_lookup_and_cancels_batch(window, app, tmp_path, monkeypatch):
    from tests.integration.test_country_gui import configure, install_runner, report
    from world_address_engine.gui import country_lookup
    configure(window, tmp_path)
    entered, release, batch_started, lookup_closed = (threading.Event() for _ in range(4))
    class Session:
        status = 'Verified'
        def __init__(self, *args): pass
        def lookup(self, text):
            entered.set()
            release.wait(3)
            return {'code': 'JP', 'name': 'Japan', 'status': 'DETERMINED', 'zone': '3', 'novsn': 'F'}
        def close(self): lookup_closed.set()
    monkeypatch.setattr(country_lookup, 'LookupSession', Session)
    def analyze(*args, cancel_requested, **kwargs):
        batch_started.set()
        while not cancel_requested():
            time.sleep(.005)
        return report('CANCELLED')
    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, batch_started.is_set)
    wait(app, lambda: window.quick.query.isEnabled())
    window.quick.address.setPlainText('Japan')
    window.quick.query.click()
    wait(app, entered.is_set)
    try:
        window.close()
        assert window._closing and window._cancel.is_set()
        assert window._lookup_thread.isRunning()
        release.set()
        wait(app, lambda: not window.busy and not window._lookup_thread.isRunning())
        assert lookup_closed.is_set() and not window.quick.copy.isEnabled()
    finally:
        release.set()


def test_enabled_missing_hk_requires_explicit_off(tmp_path):
    from world_address_engine.gui.country_lookup import LookupSession
    with pytest.raises(ValueError, match='Hong Kong'):
        LookupSession(('missing-global.db', '', True))


def test_unresolved_result_explains_reason(window):
    window.quick.show_result({'code': '', 'name': '', 'status': 'UNRESOLVED',
                              'zone': '', 'novsn': '', 'reason': 'No address text.'})
    assert 'Reason: No address text.' in window.quick.result.text()
    assert not window.quick.copy.isEnabled()


@pytest.mark.parametrize('failure_at', ['classifier', 'zones'])
def test_lookup_discards_real_address_cache_on_exception(tmp_path, monkeypatch, failure_at):
    from tests.unit.test_retrieve import geo
    from tests.integration.test_country_autopath import _global_manifest
    from world_address_engine.data import zone_mappings
    from world_address_engine.gui.country_lookup import LookupSession
    path = geo(tmp_path)
    _global_manifest(path)
    session = LookupSession((str(path), ''))
    model = session.model
    classify = model.classify

    def failing_classify(record):
        classify(record)
        raise ValueError('synthetic lookup failure')

    def failing_zones(*args):
        raise ValueError('synthetic lookup failure')

    try:
        with monkeypatch.context() as patch:
            if failure_at == 'classifier':
                patch.setattr(model, 'classify', failing_classify)
            else:
                patch.setattr(zone_mappings, 'zone_values', failing_zones)
            with pytest.raises(ValueError, match='synthetic lookup failure'):
                session.lookup('Tokyo Japan')
            assert not model._cache and model._cache_text_bytes == 0
        assert session.lookup('China')['code'] == 'CN'
        assert session.model is model
        assert not model._cache and model._cache_text_bytes == 0
    finally:
        session.close()
