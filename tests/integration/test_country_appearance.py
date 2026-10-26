"""Persistent appearance preferences, isolated from the operator's settings."""
import gc
import os
from pathlib import Path
import weakref

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QPalette  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QLabel, QWidget  # noqa: E402

from tests.integration.test_country_gui import app, wait  # noqa: E402,F401
from world_address_engine.gui import country_app  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    from world_address_engine.gui import country_paths
    monkeypatch.setattr(country_paths, 'discovery_roots', lambda: (tmp_path,))
    path = str(tmp_path / 'appearance.ini')
    # Patch the constructor lookup, including windows opened without injection.
    monkeypatch.setattr(country_app, 'QSettings',
                        lambda *args: QSettings(path, QSettings.Format.IniFormat), raising=False)
    return path


@pytest.fixture
def window(app):
    instance = country_app.CountryAnalysisWindow()
    yield instance
    instance.close()
    wait(app, lambda: not instance._lookup_thread.isRunning())
    app.processEvents()


def choose(window, mode):
    window.appearance.setCurrentIndex(window.appearance.findData(mode))


def system_palette(app, dark):
    palette = QPalette(app.palette())
    palette.setColor(QPalette.ColorRole.Window, QColor('#101820' if dark else '#f5f7fa'))
    app.setPalette(palette)
    app.processEvents()


def test_default_selector_is_visible_labeled_and_keyboard_operable(window, app):
    window.show()
    app.processEvents()
    selector = window.appearance
    assert selector.isVisible()
    assert selector.accessibleName() == 'Appearance'
    assert [selector.itemText(i) for i in range(selector.count())] == ['System', 'Light', 'Dark']
    assert selector.currentData() == 'system'
    labels = [label for label in window.findChildren(QLabel) if label.buddy() is selector]
    assert len(labels) == 1 and labels[0].isVisible()
    assert labels[0].text().replace('&', '') == 'Appearance'
    selector.setFocus()
    QTest.keyClick(selector, Qt.Key.Key_Down)
    assert selector.currentData() == 'light'
    assert window.property('workbenchTheme') == 'light'


@pytest.mark.parametrize('mode', ['system', 'light', 'dark'])
def test_selection_survives_new_window_and_new_settings_instance(app, isolated_settings, mode):
    first = country_app.CountryAnalysisWindow()
    choose(first, 'dark' if mode == 'system' else 'system')
    choose(first, mode)
    first.close()
    del first
    saved = QSettings(isolated_settings, QSettings.Format.IniFormat)
    assert saved.value('appearance/mode') == mode
    restarted = country_app.CountryAnalysisWindow()
    try:
        assert restarted.appearance.currentData() == mode
        if mode != 'system':
            assert restarted.property('workbenchTheme') == mode
    finally:
        restarted.close()


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_explicit_mode_resists_system_changes_then_system_uses_current_palette(window, app, mode):
    from world_address_engine.gui.presentation import palette_tokens
    original = QPalette(app.palette())
    try:
        choose(window, mode)
        for dark in (True, False, True):
            system_palette(app, dark)
            assert window.property('workbenchTheme') == mode
            assert window.palette().color(QPalette.ColorRole.Window).name() == palette_tokens(mode == 'dark')['background']
        choose(window, 'system')
        assert window.property('workbenchTheme') == 'dark'
        system_palette(app, False)
        assert window.property('workbenchTheme') == 'light'
    finally:
        app.setPalette(original)
        app.processEvents()


def test_default_system_tracks_live_palette(window, app):
    original = QPalette(app.palette())
    try:
        for dark in (True, False):
            system_palette(app, dark)
            assert window.property('workbenchTheme') == ('dark' if dark else 'light')
    finally:
        app.setPalette(original)
        app.processEvents()


def test_opening_default_system_does_not_write_preferences(window, isolated_settings):
    saved = QSettings(isolated_settings, QSettings.Format.IniFormat)
    assert not saved.contains('appearance/mode')


def test_unknown_saved_value_falls_back_to_system(app, isolated_settings):
    settings = QSettings(isolated_settings, QSettings.Format.IniFormat)
    settings.setValue('appearance/mode', 'obsolete-value')
    settings.sync()
    instance = country_app.CountryAnalysisWindow()
    try:
        assert instance.appearance.currentData() == 'system'
        expected = 'dark' if app.palette().color(QPalette.ColorRole.Window).lightness() < 128 else 'light'
        assert instance.property('workbenchTheme') == expected
    finally:
        instance.close()


def test_switching_is_scoped_and_does_not_change_other_windows(window, app):
    other = QWidget()
    original = QPalette(app.palette())
    other_palette, other_styles = QPalette(other.palette()), other.styleSheet()
    app_styles = app.styleSheet()
    try:
        for mode in ('dark', 'light', 'system'):
            choose(window, mode)
            assert app.palette() == original
            assert app.styleSheet() == app_styles
            assert other.palette() == other_palette
            assert other.styleSheet() == other_styles
    finally:
        other.close()


@pytest.mark.parametrize('size', [9, 14, 18])
def test_selector_stays_visible_at_compact_size_and_large_text(window, app, size):
    window.setFont(QFont(window.font().family(), size))
    window.resize(960, 720)
    window.show()
    app.processEvents()
    assert window.width() <= 960
    for control in (window.appearance, window.input_toggle):
        assert control.isVisible()
        top_left = control.mapTo(window.centralWidget(), control.rect().topLeft())
        bottom_right = control.mapTo(window.centralWidget(), control.rect().bottomRight())
        assert window.centralWidget().rect().contains(top_left)
        assert window.centralWidget().rect().contains(bottom_right)


def test_header_reflows_when_text_grows_without_resizing_window(window, app):
    window.resize(960, 720)
    window.show()
    app.processEvents()
    window.setFont(QFont(window.font().family(), 18))
    for _ in range(3):
        app.processEvents()
    header = window.centralWidget().layout().itemAt(0).widget()
    assert header._compact
    assert window.width() == 960
    assert header.rect().contains(window.appearance.mapTo(header, window.appearance.rect().bottomRight()))
    assert header.rect().contains(window.input_toggle.mapTo(header, window.input_toggle.rect().bottomRight()))


@pytest.fixture
def segoe_ui_font(app):
    path = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'Fonts' / 'segoeui.ttf'
    if not path.is_file():
        pytest.skip('Installed Windows Segoe UI is required for this font regression')
    font_id = QFontDatabase.addApplicationFont(str(path))
    assert font_id >= 0
    try:
        assert 'Segoe UI' in QFontDatabase.applicationFontFamilies(font_id)
        yield 'Segoe UI'
    finally:
        QFontDatabase.removeApplicationFont(font_id)


@pytest.mark.parametrize('grow_after_show', [False, True])
def test_real_segoe_ui_header_preserves_both_identity_lines_at_18pt(
        window, app, segoe_ui_font, grow_after_show):
    window.setFont(QFont(segoe_ui_font, 9 if grow_after_show else 18))
    window.resize(960, 720)
    window.show()
    app.processEvents()
    if grow_after_show:
        window.setFont(QFont(segoe_ui_font, 18))
    for _ in range(4):
        app.processEvents()
    header = window.centralWidget().layout().itemAt(0).widget()
    labels = header.items[1].findChildren(QLabel)
    assert len(labels) == 2
    for label in labels:
        assert QFontInfo(label.font()).family() == segoe_ui_font
        required = label.fontMetrics().horizontalAdvance(label.text())
        assert label.contentsRect().width() >= required, (label.text(), label.width(), required)
    assert header._compact
    assert window.width() == 960 and window.height() == 720
    for control in (window.appearance, window.input_toggle):
        assert header.rect().contains(control.mapTo(header, control.rect().bottomRight()))
    identity_rect = header.items[1].geometry()
    assert not identity_rect.intersects(header.items[2].geometry())
    assert not identity_rect.intersects(header.items[3].geometry())


def test_settings_and_palette_connections_do_not_retain_closed_window(app):
    collecting = gc.isenabled()
    gc.disable()
    try:
        instance = country_app.CountryAnalysisWindow()
        choose(instance, 'dark')
        choose(instance, 'system')
        instance.close()
        reference = weakref.ref(instance)
        del instance
        app.processEvents()
        assert reference() is None
    finally:
        gc.collect()
        if collecting:
            gc.enable()
