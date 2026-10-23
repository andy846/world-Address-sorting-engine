"""Synthetic results UI: pending is not the same thing as inferred."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication  # noqa: E402


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


def test_closed_panel_has_no_python_reference_cycle(app):
    import gc
    import weakref
    from world_address_engine.gui.country_results import CountryResultsPanel
    collecting = gc.isenabled()
    gc.disable()
    try:
        widget = CountryResultsPanel()
        reference = weakref.ref(widget)
        widget.close()
        del widget
        app.processEvents()
        assert reference() is None
    finally:
        gc.collect()
        if collecting:
            gc.enable()
