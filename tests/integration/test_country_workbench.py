"""Presentation contracts; synthetic paths and inputs only."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QScrollArea, QSplitter, QWidget  # noqa: E402

from tests.integration.test_country_gui import app, window  # noqa: E402,F401


def contrast(first, second):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + .05) / (a + .05)


@pytest.mark.parametrize('dark', [False, True])
def test_workbench_palette_has_readable_text_controls_and_semantic_colors(dark):
    from world_address_engine.gui.presentation import palette_tokens
    tokens = palette_tokens(dark)
    for foreground, backgrounds in (
            ('text', ('background', 'surface', 'raised')),
            ('muted', ('background', 'surface', 'raised')),
            ('on_primary', ('primary',)),
            ('warning', ('warning_surface',)),
            ('success', ('success_surface',)),
            ('inferred', ('inferred_surface',))):
        for background in backgrounds:
            assert contrast(tokens[foreground], tokens[background]) >= 4.5, (foreground, background, dark)
    assert contrast(tokens['focus'], tokens['surface']) >= 3


def test_workbench_is_resizable_side_by_side_with_scrollable_settings(window, app):
    window.show()
    app.processEvents()
    assert isinstance(window.workbench, QSplitter)
    assert window.workbench.orientation() == Qt.Orientation.Horizontal
    assert isinstance(window.settings_scroll, QScrollArea)
    assert window.settings_scroll.widgetResizable()
    assert window.settings_scroll.widget() is window.inputs
    assert window.workbench.widget(0) is window.settings_scroll
    assert window.results.isVisible()
    assert window.settings_scroll.width() < window.workspace.width()
    window.input_toggle.click()
    app.processEvents()
    assert not window.settings_scroll.isVisible()
    assert window.workspace.isVisible()
    window.input_toggle.click()
    assert window.settings_scroll.isVisible()


@pytest.mark.parametrize('large_text', [False, True])
def test_compact_window_preserves_primary_actions_and_scrolls_long_settings(window, app, large_text):
    if large_text:
        font = QFont(window.font())
        font.setPointSize(14)
        window.setFont(font)
    long_path = 'C:/' + 'example-very-long-folder/' * 15 + 'synthetic.csv'
    window.input_path.setText(long_path)
    window.output_dir.setText(long_path + '-result')
    window.export_location.setText(long_path)
    window.source_versions.setText('Example catalogue ' * 80)
    window.address_columns.addItems([f'Address field {i}' for i in range(20)])
    window.resize(960, 720)
    window.show()
    app.processEvents()
    assert window.width() <= 960
    assert window.height() <= 720
    assert window.settings_scroll.viewport().width() > 200
    for control in (window.input_toggle, window.run_button, window.preview_button,
                    window.resume_button, window.cancel_button, window.open_output_button):
        assert control.isVisible()
        position = control.mapTo(window.centralWidget(), control.rect().center())
        assert window.centralWidget().rect().contains(position), control.text()
    window.geo_db.setFocus()
    app.processEvents()
    assert window.geo_db.hasFocus()
    assert window.settings_scroll.verticalScrollBar().maximum() > 0


def test_diagnostics_are_collapsed_but_errors_reveal_details(window, app):
    window.show()
    app.processEvents()
    assert not window.diagnostics_toggle.isChecked()
    assert not window.diagnostics.isVisible()
    window._operation_failed('Synthetic offline failure')
    assert window.diagnostics_toggle.isChecked()
    assert window.diagnostics.isVisible()
    assert 'Synthetic offline failure' in window.log.toPlainText()
    window.diagnostics_toggle.click()
    assert not window.diagnostics.isVisible()


def test_theme_is_scoped_to_window_and_retains_accessible_names(window, app):
    from world_address_engine.gui.presentation import apply_workbench_theme
    other = QWidget()
    old_app_styles = app.styleSheet()
    try:
        apply_workbench_theme(window, dark=True)
        assert window.property('workbenchTheme') == 'dark'
        assert app.styleSheet() == old_app_styles
        assert not other.styleSheet()
        assert 'focus' in window.styleSheet()
        for field in (window.input_path, window.output_dir, window.geo_db, window.encoding,
                      window.sheet_name, window.address_columns):
            assert field.accessibleName()
        assert window.address_columns.selectionMode().name == 'MultiSelection'
    finally:
        other.close()


def test_progress_text_is_outside_the_colored_bar_and_never_early_complete(window):
    assert not window.progress.isTextVisible()
    window._on_stage_event({'stage': 'exporting', 'processed': 5, 'committed': 6, 'total': 6})
    assert window.progress_percent.text() == '83% of stage'
    window._on_stage_event({'stage': 'exporting', 'processed': 6, 'committed': 6, 'total': 6})
    assert window.progress_percent.text() == '99% of stage'
    window._on_stage_event({'stage': 'finalizing', 'processed': 6, 'committed': 6, 'total': 6})
    assert window.progress_percent.text() == 'Working...'


@pytest.mark.parametrize('dark', [True, False])
def test_rendered_results_and_case_backgrounds_match_theme_tokens(window, app, dark):
    from world_address_engine.gui.presentation import apply_workbench_theme, palette_tokens
    apply_workbench_theme(window, dark=dark)
    window.show()
    app.processEvents()
    image = window.results.grab().toImage()
    assert image.pixelColor(image.width() - 2, 1).name() == palette_tokens(dark)['background']
    window.results.tabs.setCurrentIndex(1)
    app.processEvents()
    page = window.results.tabs.widget(1).grab().toImage()
    assert page.pixelColor(page.width() - 3, page.height() - 3).name() == palette_tokens(dark)['surface']


def test_large_native_text_reaches_controls_even_after_retheming(window, app):
    from world_address_engine.gui.presentation import apply_workbench_theme
    window.setFont(QFont(window.font().family(), 14))
    app.processEvents()
    for dark in (True, False):
        apply_workbench_theme(window, dark=dark)
        app.processEvents()
        assert window.input_path.font().pointSizeF() == 14
        assert window.run_button.font().pointSizeF() == 14
        assert window.results.font().pointSizeF() == 14
        assert window.results.pending_value.font().pointSizeF() == pytest.approx(25.2)


def test_desktop_workspace_does_not_scroll_when_its_minimum_content_fits(window, app):
    window.resize(1280, 820)
    window.show()
    app.processEvents()
    assert window.workspace.minimumSizeHint().height() <= window.workspace_scroll.viewport().height()
    assert window.workspace_scroll.verticalScrollBar().maximum() == 0


def test_dark_table_gutter_does_not_retain_light_system_background(window, app):
    from world_address_engine.gui.presentation import apply_workbench_theme, palette_tokens
    apply_workbench_theme(window, dark=True)
    window.counts.setRowCount(1)
    window.show()
    app.processEvents()
    gutter = window.counts.verticalHeader().viewport().grab().toImage()
    tokens = palette_tokens(True)
    assert gutter.pixelColor(5, gutter.height() - 5).name() in (tokens['raised'], tokens['background'])


def test_initial_case_failure_is_visible_partial_success_and_retry_clears_warning(window, app):
    from tests.integration.test_country_gui import report
    window.show()
    window._apply_analysis({'report': report(), 'rows': [('JP', 'Japan', 5)],
                            'case_error': 'Synthetic checksum verification failure'})
    app.processEvents()
    assert window.job_state == 'done'
    assert window.diagnostics_toggle.isChecked()
    assert window.diagnostics.isVisible()
    assert 'unavailable' in window.activity.text().lower()
    assert 'unavailable' in window.results.headline.text().lower()
    assert 'case' in window.statusBar().currentMessage().lower()
    assert 'checksum' in window.log.toPlainText().lower()
    window._case_after_record = 0
    window._apply_case_page({'rows': [], 'has_next': False, 'next_cursor': 0})
    assert 'unavailable' not in window.results.headline.text().lower()


@pytest.mark.parametrize('kind', ['csv', 'xlsx'])
def test_workbench_reports_equal_direct_runner_with_reversed_column_clicks(window, app, tmp_path, kind):
    import csv
    from tests.unit.test_retrieve import geo
    from tests.integration.test_country_gui import wait
    from world_address_engine.jobs.country_analysis import analyze_job
    columns = [f'NAME_ADDRESS_LINE{i}' for i in range(1, 6)]
    rows = [columns + ['Control no'],
            ['Sample Person', '12 Example Road', 'Example district', '', 'China', '001'],
            ['Sample Person', 'Flat 1', 'Kowloon', '', 'Hong Kong', '002'],
            ['', '', '', '', '', '003']]
    source = tmp_path / f'synthetic.{kind}'
    options = {}
    if kind == 'csv':
        with source.open('w', encoding='utf-8-sig', newline='') as stream:
            csv.writer(stream).writerows(rows)
    else:
        from openpyxl import Workbook
        book = Workbook()
        book.active.title = 'Addresses'
        for row in rows:
            book.active.append(row)
        book.save(source)
        book.close()
        options = {'sheet_name': 'Addresses'}
    pack = geo(tmp_path)
    baseline, actual = tmp_path / 'direct', tmp_path / 'gui'
    report = analyze_job(source, baseline, pack, options)
    original = source.read_bytes()
    window.input_path.setText(str(source))
    window.output_dir.setText(str(actual))
    window.geo_db.setText(str(pack))
    window.address_columns.addItems(columns)
    for index in (4, 3, 2, 1, 0):
        window.address_columns.item(index).setSelected(True)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'done', window.log.toPlainText()
    assert window._last_report['status_counts'] == report['status_counts']
    assert report['status_counts'] == {'DETERMINED': 2, 'INFERRED': 0, 'UNRESOLVED': 1}
    for name in ('Classified_Addresses.csv', 'Country_Diagnostics.csv', 'Country_Summary.csv'):
        assert (baseline / name).read_bytes() == (actual / name).read_bytes()
    assert source.read_bytes() == original
