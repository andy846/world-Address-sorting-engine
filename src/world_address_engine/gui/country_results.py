"""Native completion overview and bounded, read-only country case pages."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QHeaderView, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from world_address_engine.gui.country_cases import PAGE_SIZE


class CountryResultsPanel(QWidget):
    pageRequested = Signal(str, int)
    exportRequested = Signal(str)

    def __init__(self):
        super().__init__()
        self._ready = False
        self._busy = False
        self._history = [0]
        self._page_index = 0
        self._next_cursor = 0
        self._has_next = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.headline = QLabel('Results will appear after analysis finishes.')
        layout.addWidget(self.headline)
        metrics = QGridLayout()
        for index, (name, caption) in enumerate((
                ('total', 'Total records'), ('determined', 'Determined'),
                ('inferred', 'Inferred (estimated)'), ('pending', 'Needs attention'))):
            label = QLabel(caption)
            value = QLabel('-')
            value.setTextFormat(Qt.TextFormat.PlainText)
            font = value.font()
            font.setPointSize(max(font.pointSize(), 10) + 5)
            font.setBold(True)
            value.setFont(font)
            setattr(self, f'{name}_value', value)
            metrics.addWidget(label, 0, index)
            metrics.addWidget(value, 1, index)
            metrics.setColumnStretch(index, 1)
        layout.addLayout(metrics)
        self.performance = QLabel('Coverage measures assigned codes, not accuracy.')
        self.performance.setWordWrap(True)
        layout.addWidget(self.performance)
        self.tabs = QTabWidget()
        self.counts = QTableWidget(0, 3)
        self.counts.setHorizontalHeaderLabels(['Country Code', 'Country name', 'Count'])
        self.counts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.counts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.counts, 'Country summary')
        cases = QWidget()
        case_layout = QVBoxLayout(cases)
        controls = QHBoxLayout()
        self.case_filter = QComboBox()
        for title, mode in (('Needs attention', 'pending'), ('Inferred only', 'inferred'), ('All records', 'all')):
            self.case_filter.addItem(title, mode)
        self.case_filter.currentIndexChanged.connect(self._filter_changed)
        controls.addWidget(self.case_filter)
        self.case_summary = QLabel('No completed case reports loaded.')
        controls.addWidget(self.case_summary, 1)
        self.export_button = QPushButton('Export entire filter...')
        self.export_button.clicked.connect(self._export_filter)
        controls.addWidget(self.export_button)
        case_layout.addLayout(controls)
        self.case_table = QTableWidget(0, 6)
        self.case_table.setHorizontalHeaderLabels([
            'Source record', 'Address', 'Status', 'Country code', 'Reason', 'Candidates'])
        self.case_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.case_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.case_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.case_table.setWordWrap(False)
        self.case_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.case_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.case_table.setColumnWidth(0, 100)
        self.case_table.setColumnWidth(2, 100)
        self.case_table.setColumnWidth(3, 95)
        self.case_table.setColumnWidth(4, 200)
        self.case_table.itemSelectionChanged.connect(self._show_detail)
        case_layout.addWidget(self.case_table, 1)
        self.case_detail = QPlainTextEdit()
        self.case_detail.setReadOnly(True)
        self.case_detail.setMaximumHeight(100)
        self.case_detail.setPlaceholderText('Select a case to see its full address and explanation. Local display only.')
        case_layout.addWidget(self.case_detail)
        navigation = QHBoxLayout()
        self.previous_button = QPushButton('Previous page')
        self.next_button = QPushButton('Next page')
        self.previous_button.clicked.connect(self._previous_page)
        self.next_button.clicked.connect(self._next_page)
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        note = QLabel('Source record = logical input record, not worksheet row. Blank XLSX rows may be skipped.')
        note.setWordWrap(True)
        navigation.addWidget(note, 1)
        case_layout.addLayout(navigation)
        self.tabs.addTab(cases, 'Cases needing attention')
        layout.addWidget(self.tabs, 1)
        self.reset()

    def reset(self):
        self._ready = False
        self._has_next = False
        self._history = [0]
        self._page_index = 0
        self._next_cursor = 0
        self.counts.setRowCount(0)
        self.case_table.setRowCount(0)
        self.case_detail.clear()
        self.case_filter.blockSignals(True)
        self.case_filter.setCurrentIndex(0)
        self.case_filter.blockSignals(False)
        self.case_summary.setText('No completed case reports loaded.')
        self.headline.setText('Results will appear after analysis finishes.')
        self.performance.setText('Coverage measures assigned codes, not accuracy.')
        for name in ('total', 'determined', 'inferred', 'pending'):
            getattr(self, f'{name}_value').setText('-')
        self.tabs.setCurrentIndex(0)
        self.set_busy(self._busy)

    def show_report(self, report, elapsed):
        total = report.get('total_records', 0)
        counts = report.get('status_counts', {})
        pending = counts.get('UNRESOLVED', 0)
        self.total_value.setText(f'{total:,}')
        for name, status in (('determined', 'DETERMINED'), ('inferred', 'INFERRED'), ('pending', 'UNRESOLVED')):
            getattr(self, f'{name}_value').setText(f'{counts.get(status, 0):,}')
        self.headline.setText('Analysis complete - cases need attention.' if pending else 'Analysis complete - no pending cases.')
        coverage = (total - pending) * 100 / total if total else 0
        self.performance.setText(
            f'{len(report.get("destination_counts", {})):,} countries | Elapsed: {elapsed:.2f} s | '
            f'Code coverage: {coverage:.2f}% (not accuracy). Inferred codes are estimates, not failed cases.')
        self._ready = True
        self.tabs.setCurrentIndex(1 if pending else 0)
        self.set_busy(self._busy)

    def set_busy(self, busy):
        self._busy = busy
        active = self._ready and not busy
        self.case_filter.setEnabled(active)
        self.export_button.setEnabled(active)
        self.previous_button.setEnabled(active and self._page_index > 0)
        self.next_button.setEnabled(active and self._has_next)

    def _filter_changed(self):
        self.case_table.setRowCount(0)
        self.case_detail.clear()
        self._history, self._page_index, self._has_next = [0], 0, False
        self.case_summary.setText('Loading selected filter...')
        if self._ready and not self._busy:
            self.pageRequested.emit(self.case_filter.currentData(), 0)

    def _export_filter(self):
        self.exportRequested.emit(self.case_filter.currentData())

    def _previous_page(self):
        if self._page_index > 0:
            self.pageRequested.emit(self.case_filter.currentData(), self._history[self._page_index - 1])

    def _next_page(self):
        if self._has_next:
            self.pageRequested.emit(self.case_filter.currentData(), self._next_cursor)

    def apply_page(self, page, after_record=0):
        rows = page['rows']
        if len(rows) > PAGE_SIZE:
            raise ValueError('Case page exceeds the display limit.')
        if after_record in self._history:
            self._page_index = self._history.index(after_record)
        else:
            self._history = self._history[:self._page_index + 1] + [after_record]
            self._page_index += 1
        self._next_cursor, self._has_next = page['next_cursor'], page['has_next']
        self.case_detail.clear()
        self.case_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row['record_no'], row['address'].replace('\n', ' / '), row['status'],
                      row['code'], row['reason'], row['candidates'])
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value)[:500])
                self.case_table.setItem(index, column, item)
            self.case_table.item(index, 0).setData(Qt.ItemDataRole.UserRole, row)
        self.case_summary.setText(
            f'Page {self._page_index + 1}: {len(rows)} cases shown (max {PAGE_SIZE}).'
            if rows else 'No cases match this filter.')
        self.set_busy(self._busy)

    def _show_detail(self):
        selected = self.case_table.selectedItems()
        if not selected:
            self.case_detail.clear()
            return
        item = self.case_table.item(selected[0].row(), 0)
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if row:
            self.case_detail.setPlainText(
                f'Source record {row["record_no"]} | {row["status"]} | Country: {row["code"] or "not assigned"}\n'
                f'{row["explanation"]} [{row["reason"]}]\n'
                f'Candidates: {row["candidates"] or "none"}\n{row["address"]}')
