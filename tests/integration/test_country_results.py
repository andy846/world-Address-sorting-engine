"""Synthetic results UI: pending is not the same thing as inferred."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QFrame, QGridLayout, QHeaderView,
    QLabel, QSplitter, QStyleOptionViewItem, QTableWidgetItem,
)


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    from world_address_engine.gui.country_results import CountryResultsPanel
    widget = CountryResultsPanel()
    yield widget
    widget.close()
    app.processEvents()


def sample_report():
    return {'total_records': 5, 'status_counts': {'DETERMINED': 2, 'INFERRED': 2, 'UNRESOLVED': 1},
            'destination_counts': {'JP': 2, 'HK': 2}}


def row(number=2):
    return {'record_no': number, 'address': '<b>literal</b>\nExample address', 'code': '',
            'status': 'UNRESOLVED', 'reason': 'EMPTY_ADDRESS', 'explanation': 'No address text.',
            'candidates': ''}


def test_completion_metrics_distinguish_pending_from_inferred(panel):
    panel.show_report(sample_report(), 2.5)
    assert panel.total_value.text() == '5'
    assert panel.pending_value.text() == '1'
    assert panel.inferred_value.text() == '2'
    assert '80.00%' in panel.performance.text()
    assert 'not accuracy' in panel.performance.text().lower()
    assert '2.50 s' in panel.performance.text()
    assert panel.case_filter.currentData() == 'pending'
    assert panel.tabs.currentIndex() == 1


def test_empty_completed_report_has_no_division_by_zero_or_stale_data(panel):
    panel.show_report(sample_report(), 1)
    panel.apply_page({'rows': [row()], 'has_next': False, 'next_cursor': 2})
    panel.reset()
    assert panel.case_table.rowCount() == 0
    assert not panel.export_button.isEnabled()
    panel.show_report({'total_records': 0, 'status_counts': {}, 'destination_counts': {}}, 0)
    panel.apply_page({'rows': [], 'has_next': False, 'next_cursor': 0})
    assert panel.pending_value.text() == '0'
    assert 'No cases' in panel.case_summary.text()
    assert not panel.next_button.isEnabled()


def test_page_navigation_and_filter_emit_requests_and_show_literal_details(panel):
    panel.show_report(sample_report(), 1)
    requested = []
    panel.pageRequested.connect(lambda mode, after: requested.append((mode, after)))
    panel.apply_page({'rows': [row()], 'has_next': True, 'next_cursor': 2})
    panel.case_table.selectRow(0)
    assert '<b>literal</b>' in panel.case_detail.toPlainText()
    panel.next_button.click()
    assert requested[-1] == ('pending', 2)
    panel.apply_page({'rows': [row(4)], 'has_next': False, 'next_cursor': 4}, after_record=2)
    panel.previous_button.click()
    assert requested[-1] == ('pending', 0)
    panel.case_filter.setCurrentIndex(1)
    assert requested[-1] == ('inferred', 0)
    assert panel.case_table.rowCount() == 0


def test_busy_controls_and_reset_cannot_retain_previous_case(panel):
    panel.show_report(sample_report(), 1)
    panel.apply_page({'rows': [row()], 'has_next': True, 'next_cursor': 2})
    panel.set_busy(True)
    assert not panel.case_filter.isEnabled()
    assert not panel.next_button.isEnabled()
    assert not panel.export_button.isEnabled()
    panel.reset()
    panel.set_busy(False)
    assert panel.case_table.rowCount() == 0
    assert not panel.export_button.isEnabled()


def test_page_rows_are_bounded_and_not_editable(panel):
    from PySide6.QtWidgets import QAbstractItemView
    panel.show_report(sample_report(), 1)
    with pytest.raises(ValueError):
        panel.apply_page({'rows': [row()] * 101, 'has_next': True, 'next_cursor': 2})
    assert panel.case_table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


def test_metric_cards_expose_semantic_roles_and_accessible_values(panel):
    assert isinstance(panel.metrics_grid, QGridLayout)
    assert len(panel.metric_cards) == 4
    for card, name, tone in zip(panel.metric_cards,
                                ('total', 'determined', 'inferred', 'pending'),
                                ('neutral', 'success', 'inferred', 'warning')):
        assert isinstance(card, QFrame)
        assert card.property('workbenchRole') == 'metricCard'
        assert card.property('tone') == tone
        assert panel.isAncestorOf(card)
        assert card.objectName()
        value = getattr(panel, f'{name}_value')
        assert value.parentWidget() is card
        assert value.property('workbenchRole') == 'metricValue'
        assert value.textFormat() == Qt.TextFormat.PlainText
        assert value.alignment() & Qt.AlignmentFlag.AlignRight
        assert value.accessibleName()
        captions = [label for label in card.findChildren(QLabel) if label is not value]
        assert len(captions) == 1
        assert captions[0].property('workbenchRole') == 'muted'
        assert captions[0].font().pointSizeF() == panel.font().pointSizeF()


def test_metric_grid_reflows_both_directions_without_changing_numbers(panel, app):
    panel.show_report({'total_records': 10002,
                       'status_counts': {'DETERMINED': 9000, 'INFERRED': 1000, 'UNRESOLVED': 2},
                       'destination_counts': {'JP': 10000}}, 2.5)
    panel.show()
    for width, positions in (
            (750, [(0, 0), (0, 1), (0, 2), (0, 3)]),
            (500, [(0, 0), (0, 1), (1, 0), (1, 1)]),
            (700, [(0, 0), (0, 1), (0, 2), (0, 3)]),
            (699, [(0, 0), (0, 1), (1, 0), (1, 1)]),
            (1000, [(0, 0), (0, 1), (0, 2), (0, 3)]),
            (500, [(0, 0), (0, 1), (1, 0), (1, 1)])):
        panel.resize(width, 800)
        app.processEvents()
        assert panel.width() == width
        assert panel.metrics_grid.count() == 4
        assert [panel.metrics_grid.getItemPosition(panel.metrics_grid.indexOf(card))[:2]
                for card in panel.metric_cards] == positions
        assert [getattr(panel, f'{name}_value').text()
                for name in ('total', 'determined', 'inferred', 'pending')] == [
                    '10,002', '9,000', '1,000', '2']
        assert '99.98%' in panel.performance.text()
        assert all(card.width() > 0 and card.geometry().right() < panel.width()
                   for card in panel.metric_cards)


@pytest.mark.parametrize('point_size', [11, 17])
def test_metric_font_scales_with_native_panel_font(panel, point_size):
    font = panel.font()
    font.setPointSizeF(point_size)
    panel.setFont(font)
    for name in ('total', 'determined', 'inferred', 'pending'):
        value_font = getattr(panel, f'{name}_value').font()
        assert value_font.family() == panel.font().family()
        assert value_font.pointSizeF() == pytest.approx(point_size * 1.8)


def test_case_splitter_has_usable_resizable_panes_and_full_literal_details(panel, app):
    panel.resize(500, 800)
    panel.show_report(sample_report(), 1)
    literal = '<b>literal</b>\n' + 'Synthetic address line\n' * 80
    rows = [dict(row(number), address=literal) for number in range(1, 101)]
    panel.apply_page({'rows': rows, 'has_next': True, 'next_cursor': 100})
    panel.show()
    app.processEvents()
    assert isinstance(panel.case_splitter, QSplitter)
    assert panel.case_splitter.orientation() == Qt.Orientation.Vertical
    assert panel.case_splitter.widget(0) is panel.case_table
    assert panel.case_splitter.widget(1) is panel.case_detail
    assert not panel.case_splitter.childrenCollapsible()
    assert all(size >= 64 for size in panel.case_splitter.sizes())
    panel.case_splitter.setSizes([200, 200])
    app.processEvents()
    assert panel.case_detail.height() > 100
    panel.case_table.selectRow(99)
    assert panel.case_table.rowCount() == 100
    assert panel.case_detail.isReadOnly()
    assert panel.case_detail.toPlainText().endswith(literal)
    assert 'Source record 100' in panel.case_detail.toPlainText()
    assert panel.case_splitter.accessibleName()
    assert panel.case_detail.accessibleName()


@pytest.mark.parametrize('point_size', [10, 16])
def test_narrow_case_toolbar_keeps_actions_and_summary_on_separate_rows(panel, app, point_size):
    font = panel.font()
    font.setPointSize(point_size)
    panel.setFont(font)
    panel.resize(500, 800)
    panel.show_report(sample_report(), 1)
    panel.apply_page({'rows': [row()], 'has_next': False, 'next_cursor': 2})
    panel.show()
    app.processEvents()
    assert panel.width() == 500
    assert panel.case_summary.wordWrap()
    summary_top = panel.case_summary.mapTo(panel, panel.case_summary.rect().topLeft()).y()
    for widget in (panel.case_filter, panel.export_button):
        bottom_right = widget.mapTo(panel, widget.rect().bottomRight())
        assert widget.isVisible() and widget.isEnabled()
        assert bottom_right.x() < 500
        assert bottom_right.y() < summary_top
    for widget in (panel.tabs, panel.counts, panel.case_table, panel.case_filter,
                   panel.export_button, panel.previous_button, panel.next_button):
        assert widget.accessibleName()
        assert panel.isAncestorOf(widget)
    assert all(size >= 64 for size in panel.case_splitter.sizes())


def test_country_table_gives_name_space_and_aligns_numeric_counts_without_sorting(panel):
    header = panel.counts.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.ResizeToContents
    assert panel.counts.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
    assert panel.counts.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert not panel.counts.isSortingEnabled()
    panel.counts.setRowCount(2)
    for index, values in enumerate((('JP', 'Japan', '2'), ('HK', 'Hong Kong', '10'))):
        for column, value in enumerate(values):
            panel.counts.setItem(index, column, QTableWidgetItem(value))
    option = QStyleOptionViewItem()
    delegate = panel.counts.itemDelegateForColumn(2)
    assert delegate is not None
    delegate.initStyleOption(option, panel.counts.model().index(0, 2))
    assert option.displayAlignment & Qt.AlignmentFlag.AlignRight
    assert [panel.counts.item(i, 2).text() for i in range(2)] == ['2', '10']
    panel.counts.selectRow(0)
    assert len(panel.counts.selectedItems()) == 3


def test_closed_panel_has_no_python_reference_cycle(app):
    import gc
    import weakref
    from world_address_engine.gui.country_results import CountryResultsPanel
    collecting = gc.isenabled()
    gc.disable()
    try:
        widget = CountryResultsPanel()
        widget.show()
        widget.resize(500, 800)
        app.processEvents()
        widget.resize(750, 800)
        app.processEvents()
        reference = weakref.ref(widget)
        widget.close()
        del widget
        app.processEvents()
        assert reference() is None
    finally:
        gc.collect()
        if collecting:
            gc.enable()


def test_metric_accessible_names_include_current_values(panel):
    from PySide6.QtGui import QAccessible
    panel.show_report({'total_records': 1_000_000,
                       'status_counts': {'DETERMINED': 800_000, 'INFERRED': 199_000, 'UNRESOLVED': 1000},
                       'destination_counts': {'HK': 999_000}}, 1)
    for name, number in (('total', '1,000,000'), ('determined', '800,000'),
                         ('inferred', '199,000'), ('pending', '1,000')):
        interface = QAccessible.queryAccessibleInterface(getattr(panel, f'{name}_value'))
        assert number in interface.text(QAccessible.Text.Name)
    panel.reset()
    assert 'not available' in panel.total_value.accessibleName()


@pytest.mark.parametrize('point_size,number', [(14, 10_000_000), (18, 1_000_000)])
def test_large_totals_reflow_without_clipping_leading_digits(panel, app, point_size, number):
    from PySide6.QtGui import QFont, QFontDatabase
    if os.name == 'nt':
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        panel.setFont(QFont('Segoe UI', point_size))
    else:
        font = panel.font()
        font.setPointSize(point_size)
        panel.setFont(font)
    panel.resize(718, 850)
    panel.show()
    panel.show_report({'total_records': number, 'status_counts': {'DETERMINED': number},
                       'destination_counts': {'HK': number}}, 1)
    app.processEvents()
    for name in ('total', 'determined', 'inferred', 'pending'):
        value = getattr(panel, f'{name}_value')
        assert value.width() >= value.fontMetrics().horizontalAdvance(value.text())
    assert panel._metric_columns <= 2
    panel.resize(300, 850)
    app.processEvents()
    assert panel._metric_columns == 1
    assert panel.total_value.width() >= panel.total_value.fontMetrics().horizontalAdvance(panel.total_value.text())
