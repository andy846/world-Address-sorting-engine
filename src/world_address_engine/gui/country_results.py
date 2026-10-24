"""Native completion overview and bounded, read-only country case pages."""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHeaderView, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QSizePolicy, QSplitter, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from world_address_engine.gui.country_cases import PAGE_SIZE


class _CountDelegate(QStyledItemDelegate):
    """Align counts supplied by the controller without altering their data."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class CountryResultsPanel(QWidget):
    pageRequested = Signal(str, int)
    exportRequested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName('countryResults')
        self.setAccessibleName('Country analysis results')
        self._ready = False
        self._busy = False
        self._history = [0]
        self._page_index = 0
        self._next_cursor = 0
        self._has_next = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.headline = QLabel('Results will appear after analysis finishes.', self)
        self.headline.setObjectName('resultsHeadline')
        self.headline.setWordWrap(True)
        layout.addWidget(self.headline)
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(8)
        self.metric_cards = []
        self._metric_captions = {}
        self._metric_columns = 0
        for name, caption, tone in (
                ('total', 'Total records', 'neutral'), ('determined', 'Determined', 'success'),
                ('inferred', 'Inferred (estimated)', 'inferred'),
                ('pending', 'Needs attention', 'warning')):
            self._metric_captions[name] = caption
            card = QFrame(self)
            card.setObjectName(f'{name}MetricCard')
            card.setProperty('workbenchRole', 'metricCard')
            card.setProperty('tone', tone)
            card.setAccessibleName(caption)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(4)
            label = QLabel(caption, card)
            label.setProperty('workbenchRole', 'muted')
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            value = QLabel('-', card)
            value.setObjectName(f'{name}MetricValue')
            value.setProperty('workbenchRole', 'metricValue')
            value.setAccessibleName(caption)
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            setattr(self, f'{name}_value', value)
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            self.metric_cards.append(card)
        self._update_metric_fonts()
        self._reflow_metrics()
        layout.addLayout(self.metrics_grid)
        self.performance = QLabel('Coverage measures assigned codes, not accuracy.', self)
        self.performance.setProperty('workbenchRole', 'muted')
        self.performance.setWordWrap(True)
        self.performance.setToolTip(
            'Coverage measures assigned codes, not accuracy. '
            'Inferred codes are estimates, not failed cases.')
        layout.addWidget(self.performance)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName('resultsTabs')
        self.tabs.setAccessibleName('Result views')
        self.tabs.setDocumentMode(True)
        self.counts = QTableWidget(0, 3, self.tabs)
        self.counts.setObjectName('countryCounts')
        self.counts.setAccessibleName('Country summary')
        self.counts.setHorizontalHeaderLabels(['Country Code', 'Country name', 'Count'])
        counts_header = self.counts.horizontalHeader()
        counts_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        counts_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        counts_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.counts.setItemDelegateForColumn(2, _CountDelegate(self.counts))
        self.counts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.counts.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.counts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.counts.setSortingEnabled(False)
        self.counts.setWordWrap(False)
        self.tabs.addTab(self.counts, 'Country summary')
        cases = QWidget(self.tabs)
        case_layout = QVBoxLayout(cases)
        case_layout.setContentsMargins(8, 8, 8, 8)
        case_layout.setSpacing(8)
        self._case_controls = QGridLayout()
        self._case_controls.setSpacing(8)
        self._case_controls_columns = 0
        self.case_filter = QComboBox(cases)
        self.case_filter.setObjectName('caseFilter')
        self.case_filter.setAccessibleName('Case filter')
        self.case_filter.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        for title, mode in (('Needs attention', 'pending'), ('Inferred only', 'inferred'), ('All records', 'all')):
            self.case_filter.addItem(title, mode)
        self.case_filter.currentIndexChanged.connect(self._filter_changed)
        self.case_summary = QLabel('No completed case reports loaded.', cases)
        self.case_summary.setObjectName('caseSummary')
        self.case_summary.setProperty('workbenchRole', 'muted')
        self.case_summary.setWordWrap(True)
        self.export_button = QPushButton('Export filter...', cases)
        self.export_button.setObjectName('exportCaseFilter')
        self.export_button.setAccessibleName('Export entire case filter')
        self.export_button.setToolTip('Export every case in the selected filter, including other pages.')
        self.export_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.export_button.clicked.connect(self._export_filter)
        case_layout.addLayout(self._case_controls)
        case_layout.addWidget(self.case_summary)
        self.case_splitter = QSplitter(Qt.Orientation.Vertical, cases)
        self.case_splitter.setObjectName('caseSplitter')
        self.case_splitter.setAccessibleName('Case list and full details')
        self.case_splitter.setChildrenCollapsible(False)
        self.case_table = QTableWidget(0, 6, self.case_splitter)
        self.case_table.setObjectName('caseTable')
        self.case_table.setAccessibleName('Cases in selected filter')
        self.case_table.setMinimumHeight(100)
        self.case_table.setHorizontalHeaderLabels([
            'Source record', 'Address', 'Status', 'Country code', 'Reason', 'Candidates'])
        self.case_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.case_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.case_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.case_table.setWordWrap(False)
        self.case_table.setSortingEnabled(False)
        self.case_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.case_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.case_table.setColumnWidth(0, 100)
        self.case_table.setColumnWidth(2, 100)
        self.case_table.setColumnWidth(3, 95)
        self.case_table.setColumnWidth(4, 200)
        self.case_table.itemSelectionChanged.connect(self._show_detail)
        self.case_detail = QPlainTextEdit(self.case_splitter)
        self.case_detail.setObjectName('caseDetail')
        self.case_detail.setAccessibleName('Full case address and explanation, local display only')
        self.case_detail.setReadOnly(True)
        self.case_detail.setMinimumHeight(64)
        self.case_detail.setPlaceholderText('Select a case to see its full address and explanation. Local display only.')
        self.case_splitter.setStretchFactor(0, 3)
        self.case_splitter.setStretchFactor(1, 1)
        self.case_splitter.setSizes([300, 120])
        case_layout.addWidget(self.case_splitter, 1)
        navigation = QHBoxLayout()
        self.previous_button = QPushButton('Previous', cases)
        self.previous_button.setAccessibleName('Previous case page')
        self.next_button = QPushButton('Next', cases)
        self.next_button.setAccessibleName('Next case page')
        self.previous_button.clicked.connect(self._previous_page)
        self.next_button.clicked.connect(self._next_page)
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        navigation.addStretch(1)
        case_layout.addLayout(navigation)
        note = QLabel('Source record = input record.', cases)
        note.setToolTip(
            'Source record = logical input record, not worksheet row. Blank XLSX rows may be skipped.')
        note.setProperty('workbenchRole', 'muted')
        note.setWordWrap(True)
        case_layout.addWidget(note)
        self.tabs.addTab(cases, 'Cases')
        layout.addWidget(self.tabs, 1)
        self._reflow_case_controls()
        self.reset()

    def _update_metric_fonts(self):
        font = self.font()
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 1.8)
        else:
            font.setPixelSize(round(font.pixelSize() * 1.8))
        font.setBold(True)
        for name in ('total', 'determined', 'inferred', 'pending'):
            getattr(self, f'{name}_value').setFont(font)
        self._reflow_metrics()

    def _set_metric_value(self, name, text):
        label = getattr(self, f'{name}_value')
        label.setText(text)
        spoken = 'not available' if text == '-' else text
        label.setAccessibleName(f'{self._metric_captions[name]}: {spoken}')
        label.setToolTip(f'{self._metric_captions[name]}: {spoken}')

    def _reflow_metrics(self):
        required = 0
        for name in self._metric_captions:
            label = getattr(self, f'{name}_value')
            number_width = label.fontMetrics().horizontalAdvance(label.text())
            # Captions may wrap; the actual number must fit without losing digits.
            required = max(required, number_width + 26)
        gap = self.metrics_grid.spacing()
        if self.width() >= max(700, required * 4 + gap * 3):
            columns = 4
        elif self.width() >= required * 2 + gap:
            columns = 2
        else:
            columns = 1
        if columns == self._metric_columns:
            return
        self._metric_columns = columns
        for card in self.metric_cards:
            self.metrics_grid.removeWidget(card)
        for column in range(4):
            self.metrics_grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, card in enumerate(self.metric_cards):
            self.metrics_grid.addWidget(card, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_metrics()
        self._reflow_case_controls()

    def _reflow_case_controls(self):
        # Ignored horizontal size policies let resize events arrive before the
        # toolbar's old arrangement can impose a minimum width on the panel.
        required = self.case_filter.sizeHint().width() + self.export_button.sizeHint().width() + 32
        columns = 2 if self.width() >= required else 1
        if columns == self._case_controls_columns:
            return
        self._case_controls_columns = columns
        self._case_controls.removeWidget(self.case_filter)
        self._case_controls.removeWidget(self.export_button)
        self._case_controls.addWidget(self.case_filter, 0, 0)
        self._case_controls.addWidget(self.export_button, 0 if columns == 2 else 1,
                                      1 if columns == 2 else 0)
        self._case_controls.setColumnStretch(0, self.case_filter.sizeHint().width())
        self._case_controls.setColumnStretch(1, self.export_button.sizeHint().width() if columns == 2 else 0)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, 'pending_value'):
            self._update_metric_fonts()
            if hasattr(self, 'export_button'):
                self._reflow_case_controls()

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
            self._set_metric_value(name, '-')
        self._reflow_metrics()
        self.tabs.setCurrentIndex(0)
        self.set_busy(self._busy)

    def show_report(self, report, elapsed):
        total = report.get('total_records', 0)
        counts = report.get('status_counts', {})
        pending = counts.get('UNRESOLVED', 0)
        self._set_metric_value('total', f'{total:,}')
        for name, status in (('determined', 'DETERMINED'), ('inferred', 'INFERRED'), ('pending', 'UNRESOLVED')):
            self._set_metric_value(name, f'{counts.get(status, 0):,}')
        self._reflow_metrics()
        self.headline.setText('Analysis complete - cases need attention.' if pending else 'Analysis complete - no pending cases.')
        coverage = (total - pending) * 100 / total if total else 0
        self.performance.setText(
            f'{len(report.get("destination_counts", {})):,} countries | {elapsed:.2f} s | '
            f'Coverage: {coverage:.2f}% (not accuracy)')
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
