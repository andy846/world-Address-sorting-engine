"""Build the native workbench while leaving job/controller logic in country_app."""
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLayout, QLineEdit, QListWidget, QPushButton, QProgressBar, QScrollArea, QSizePolicy, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)

from world_address_engine.gui.country_results import CountryResultsPanel


def _label(text, *, role=None, wrap=True):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    if role:
        label.setProperty('workbenchRole', role)
    return label


class SettingsScrollArea(QScrollArea):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn and isinstance(watched, QWidget):
            self.ensureWidgetVisible(watched, 8, 12)
        return super().eventFilter(watched, event)


class WorkspaceScrollArea(QScrollArea):
    """Use minimum content height, not QTextEdit/table preferred heights."""

    def __init__(self):
        super().__init__()
        self._fitting = False

    def _fit_widget(self):
        widget = self.widget()
        if widget is None or self._fitting:
            return
        self._fitting = True
        try:
            width = self.viewport().width()
            widget.resize(width, widget.height())
            widget.layout().activate()
            # minimumSizeHint omits wrapped QLabel height; preferred heights, on
            # the other hand, over-allocate tables and editors. Add only wrapping.
            wrapping = sum(max(0, label.heightForWidth(label.width()) - label.minimumSizeHint().height())
                           for label in widget.findChildren(QLabel)
                           if label.wordWrap() and label.isVisibleTo(widget) and label.width() > 0)
            height = max(self.viewport().height(), widget.minimumSizeHint().height() + wrapping)
            widget.resize(width, height)
        finally:
            self._fitting = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_widget()

    def eventFilter(self, watched, event):
        result = super().eventFilter(watched, event)
        if watched is self.widget() and event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.FontChange):
            self._fit_widget()
        return result


class ActionBar(QWidget):
    """Native buttons reflow instead of forcing a wider top-level window."""

    def __init__(self, buttons):
        super().__init__()
        self.buttons = buttons
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self._columns = 0
        self._reflow()

    def _reflow(self):
        required = sum(button.minimumSizeHint().width() for button in self.buttons) + 32
        columns = 4 if self.width() >= max(720, required) else 2
        if columns == self._columns:
            return
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(4):
            self.grid.setColumnStretch(column, int(column < columns))
        for index, button in enumerate(self.buttons):
            self.grid.addWidget(button, index // columns, index % columns)
        self.updateGeometry()

    def resizeEvent(self, event):
        self._reflow()
        super().resizeEvent(event)


class WorkbenchHeader(QWidget):
    """Keep appearance and input controls reachable with large native fonts."""

    def __init__(self, logo, identity, offline, appearance, toggle):
        super().__init__()
        self.items = (logo, identity, offline, appearance, toggle)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._compact = None
        self._reflow()

    def minimumSizeHint(self):
        return QSize(0, self.grid.minimumSize().height())

    def _reflow(self):
        widths = [widget.minimumSizeHint().width() for widget in self.items]
        # Ignored policies let the title shrink, but report a zero minimum.
        # Measure the labels themselves so the breakpoint preserves their text.
        identity = self.items[1]
        margins = identity.layout().contentsMargins()
        widths[1] = max(label.sizeHint().width() for label in identity.findChildren(QLabel)) + margins.left() + margins.right()
        required = sum(widths) + self.grid.horizontalSpacing() * (len(self.items) - 1)
        compact = self.width() < required
        if compact == self._compact:
            return
        self._compact = compact
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(5):
            self.grid.setColumnStretch(column, int(column == 1))
        if compact:
            for widget, row, column, span in (
                    (self.items[0], 0, 0, 1), (self.items[1], 0, 1, 2),
                    (self.items[2], 0, 3, 2), (self.items[3], 1, 1, 2),
                    (self.items[4], 1, 3, 2)):
                self.grid.addWidget(widget, row, column, 1, span)
        else:
            for column, widget in enumerate(self.items):
                self.grid.addWidget(widget, 0, column)
        self.updateGeometry()

    def resizeEvent(self, event):
        self._reflow()
        super().resizeEvent(event)


def build_workbench(w, discover_pack, discover_hk_pack):
    root = QWidget()
    root.setObjectName('workbenchRoot')
    outer = QVBoxLayout(root)
    outer.setContentsMargins(16, 12, 16, 10)
    outer.setSpacing(10)
    logo = QLabel()
    logo.setPixmap(w.windowIcon().pixmap(38, 38))
    logo.setFixedSize(40, 40)
    identity = QWidget()
    identity.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    titles = QVBoxLayout(identity)
    titles.setContentsMargins(0, 0, 0, 0)
    titles.setSpacing(0)
    title = _label('World Address Sorting Engine', wrap=False)
    title.setProperty('workbenchRole', 'title')
    font = title.font()
    font.setPointSizeF(max(12, font.pointSizeF() * 1.35))
    font.setBold(True)
    title.setFont(font)
    titles.addWidget(title)
    titles.addWidget(_label('COUNTRY ANALYSIS  /  OFFLINE WORKSPACE', role='muted', wrap=False))
    offline = _label('LOCAL ONLY', role='badge', wrap=False)
    offline.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
    offline.setToolTip('Input addresses and reference data are processed on this computer.')
    appearance_box = QWidget()
    appearance_group = QVBoxLayout(appearance_box)
    appearance_group.setContentsMargins(0, 0, 0, 0)
    appearance_group.setSpacing(2)
    w.appearance = QComboBox()
    w.appearance.setObjectName('appearanceSelector')
    w.appearance.setAccessibleName('Appearance')
    w.appearance.setToolTip('System follows your computer; Light and Dark stay as selected. Your choice is saved.')
    for text, mode in (('System', 'system'), ('Light', 'light'), ('Dark', 'dark')):
        w.appearance.addItem(text, mode)
    w.appearance.setCurrentIndex(w.appearance.findData(w._appearance_mode))
    w.appearance.currentIndexChanged.connect(w._appearance_changed)
    appearance_label = _label('&Appearance', wrap=False)
    appearance_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
    appearance_label.setBuddy(w.appearance)
    appearance_group.addWidget(appearance_label)
    appearance_group.addWidget(w.appearance)
    w.input_toggle = QPushButton('Hide input settings')
    w.input_toggle.setCheckable(True)
    w.input_toggle.setChecked(True)
    w.input_toggle.toggled.connect(w._toggle_inputs)
    outer.addWidget(WorkbenchHeader(logo, identity, offline, appearance_box, w.input_toggle))

    w.workbench = QSplitter(Qt.Orientation.Horizontal)
    w.workbench.setChildrenCollapsible(False)
    w.workbench.setHandleWidth(10)
    w.settings_scroll = SettingsScrollArea()
    w.settings_scroll.viewport().setObjectName('settingsViewport')
    w.settings_scroll.setWidgetResizable(True)
    w.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    w.settings_scroll.setMinimumWidth(260)
    w.inputs = QFrame()
    w.inputs.setProperty('workbenchRole', 'card')
    settings = QVBoxLayout(w.inputs)
    settings.setContentsMargins(14, 14, 14, 14)
    settings.setSpacing(9)
    settings.addWidget(_label('01 / INPUT SETTINGS', role='section'))
    settings.addWidget(_label('Select your file and address lines. Nothing is uploaded.', role='muted'))

    def field(label, widget, callback=None, browse_name=None):
        caption = _label(label, wrap=False)
        caption.setBuddy(widget)
        settings.addWidget(caption)
        widget.setAccessibleName(label.replace('&', ''))
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        widget.installEventFilter(w.settings_scroll)
        if callback:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(widget, 1)
            browse = QPushButton('Browse...')
            browse.setAccessibleName(browse_name or f'Browse {label}')
            browse.clicked.connect(callback)
            browse.installEventFilter(w.settings_scroll)
            row.addWidget(browse)
            settings.addLayout(row)
        else:
            settings.addWidget(widget)

    w.input_path = QLineEdit()
    w.input_path.setPlaceholderText('CSV, TXT or XLSX')
    w.output_dir = QLineEdit()
    w.output_dir.setPlaceholderText('New empty folder (or automatic)')
    for edit in (w.input_path, w.output_dir):
        edit.textChanged.connect(edit.setToolTip)
    field('Address file', w.input_path, w._choose_input, 'Choose address file')
    field('Output folder', w.output_dir, w._choose_output, 'Choose output folder')
    w.encoding = QComboBox()
    w.encoding.setEditable(True)
    w.encoding.addItems(['utf-8-sig', 'utf-8', 'big5', 'gb18030', 'cp1252'])
    field('Encoding', w.encoding)
    w.sheet_name = QLineEdit()
    w.sheet_name.setPlaceholderText('XLSX only; blank = first worksheet')
    field('Worksheet', w.sheet_name)
    w.address_columns = QListWidget()
    w.address_columns.setAccessibleName('Address columns in source order')
    w.address_columns.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
    w.address_columns.setMinimumHeight(125)
    w.address_columns.setMaximumHeight(165)
    w.address_columns.installEventFilter(w.settings_scroll)
    caption = _label('Address columns (top to bottom)')
    caption.setBuddy(w.address_columns)
    settings.addWidget(caption)
    settings.addWidget(w.address_columns)
    w.input_path.textChanged.connect(w.address_columns.clear)
    w.column_selection = _label('', role='muted')
    w.address_columns.itemSelectionChanged.connect(w._update_column_selection)
    w._update_column_selection()
    settings.addWidget(w.column_selection)
    w.preview_summary = _label('Load columns to inspect this file without showing addresses.', role='muted')
    settings.addWidget(w.preview_summary)
    settings.addWidget(_label('02 / OFFLINE REFERENCE', role='section'))
    w.geo_db = QLineEdit(discover_pack())
    w.geo_db.setPlaceholderText('Installed GeoNames SQLite pack')
    w.geo_db.setToolTip(w.geo_db.text())
    w.geo_db.textChanged.connect(w.geo_db.setToolTip)
    field('GeoNames pack', w.geo_db, w._choose_geo_db, 'Choose offline GeoNames pack')
    w.hk_enabled = QCheckBox('Enable Hong Kong address pack')
    w.hk_enabled.setAccessibleName('Enable optional Hong Kong address pack')
    w.hk_enabled.setToolTip('Optional offline bilingual lookup for unresolved addresses. Disabled by default.')
    w.hk_enabled.installEventFilter(w.settings_scroll)
    settings.addWidget(w.hk_enabled)
    w.hk_regional_db = QLineEdit(discover_hk_pack())
    w.hk_regional_db.setPlaceholderText('Optional installed ALS SQLite pack')
    w.hk_regional_db.setToolTip(w.hk_regional_db.text())
    w.hk_regional_db.textChanged.connect(w.hk_regional_db.setToolTip)
    field('Hong Kong pack (optional)', w.hk_regional_db, w._choose_hk_db,
          'Choose offline Hong Kong regional pack')
    settings.addWidget(_label('Enable to use this pack for unresolved addresses. '
                              'Resume uses the original saved pack. No online queries.', role='muted'))
    settings.addWidget(_label('Country catalogue is included automatically.', role='muted'))
    settings.addStretch(1)
    w.settings_scroll.setWidget(w.inputs)
    w.workbench.addWidget(w.settings_scroll)

    w.workspace_scroll = WorkspaceScrollArea()
    w.workspace_scroll.viewport().setObjectName('workspaceViewport')
    w.workspace_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    w.workspace = QWidget()
    w.workspace.setObjectName('workspacePanel')
    workspace = QVBoxLayout(w.workspace)
    workspace.setContentsMargins(2, 0, 2, 0)
    workspace.setSpacing(10)
    buttons = []
    for name, text, callback in (
            ('run_button', 'Analyze countries', w.start_job),
            ('preview_button', 'Preview / load columns', w.preview_input),
            ('resume_button', 'Resume', w.resume_job),
            ('cancel_button', 'Cancel', w.cancel_job)):
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.clicked.connect(callback)
        setattr(w, name, button)
        buttons.append(button)
    w.run_button.setProperty('workbenchRole', 'primary')
    w.cancel_button.setEnabled(False)
    w.action_bar = ActionBar(buttons)
    workspace.addWidget(w.action_bar)
    progress_card = QFrame()
    progress_card.setProperty('workbenchRole', 'card')
    activity = QVBoxLayout(progress_card)
    activity.setContentsMargins(12, 10, 12, 10)
    activity.setSpacing(7)
    row = QHBoxLayout()
    row.addWidget(_label('LIVE ACTIVITY', role='section'))
    w.stage_badge = _label('READY', role='muted', wrap=False)
    w.stage_badge.setAlignment(Qt.AlignmentFlag.AlignRight)
    row.addWidget(w.stage_badge)
    activity.addLayout(row)
    w.activity = _label('Ready. All address processing stays on this computer.')
    activity.addWidget(w.activity)
    w.progress = QProgressBar()
    w.progress.setAccessibleName('Current analysis stage progress')
    w.progress.setTextVisible(False)
    w.progress.setRange(0, 1)
    progress_row = QHBoxLayout()
    progress_row.addWidget(w.progress, 1)
    w.progress_percent = _label('Ready', role='muted', wrap=False)
    w.progress_percent.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
    progress_row.addWidget(w.progress_percent)
    activity.addLayout(progress_row)
    workspace.addWidget(progress_card)
    w.results = CountryResultsPanel()
    w.counts = w.results.counts
    w.results.pageRequested.connect(w._load_cases)
    w.results.exportRequested.connect(w._choose_case_export)
    workspace.addWidget(w.results, 1)
    w.workspace_scroll.setWidget(w.workspace)
    w.workbench.addWidget(w.workspace_scroll)
    w.workbench.setStretchFactor(0, 0)
    w.workbench.setStretchFactor(1, 1)
    w.workbench.setSizes([320, 900])
    outer.addWidget(w.workbench, 1)

    footer = QHBoxLayout()
    footer.setSpacing(8)
    footer.addWidget(_label('OUTPUT', role='section', wrap=False))
    w.export_location = QLineEdit('No export yet.')
    w.export_location.setObjectName('outputLocation')
    w.export_location.setAccessibleName('Current output folder')
    w.export_location.setReadOnly(True)
    w.export_location.setMinimumWidth(0)
    w.export_location.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    w.export_location.textChanged.connect(w.export_location.setToolTip)
    footer.addWidget(w.export_location, 1)
    w.open_output_button = QPushButton('Open output folder')
    w.open_output_button.setEnabled(False)
    w.open_output_button.clicked.connect(w.open_output_folder)
    footer.addWidget(w.open_output_button)
    w.diagnostics_toggle = QPushButton('Diagnostics')
    w.diagnostics_toggle.setCheckable(True)
    w.diagnostics_toggle.toggled.connect(w._toggle_diagnostics)
    footer.addWidget(w.diagnostics_toggle)
    outer.addLayout(footer)
    w.diagnostics = QFrame()
    w.diagnostics.setProperty('workbenchRole', 'card')
    details = QVBoxLayout(w.diagnostics)
    details.setContentsMargins(10, 8, 10, 8)
    details.setSpacing(5)
    w.summary = _label('No analysis loaded.', role='muted')
    w.source_versions = _label('No source versions loaded.', role='muted')
    details.addWidget(w.summary)
    details.addWidget(w.source_versions)
    w.log = QTextEdit()
    w.log.setAccessibleName('Local operation diagnostics')
    w.log.setReadOnly(True)
    w.log.document().setMaximumBlockCount(300)
    w.log.setMinimumHeight(45)
    w.log.setMaximumHeight(85)
    details.addWidget(w.log)
    w.diagnostics.setMaximumHeight(165)
    w.diagnostics.hide()
    outer.addWidget(w.diagnostics)
    w.setCentralWidget(root)
    w.statusBar().showMessage('Ready for offline country analysis.')
    w._apply_appearance()
