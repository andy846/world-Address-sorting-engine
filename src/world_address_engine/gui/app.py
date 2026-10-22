"""Offline PySide6 desktop workflow for the address classifier.

The GUI is a thin shell around the same deterministic engine the CLI uses.
Widgets never touch SQL or the network: the job runs in a worker thread so
the window stays responsive, and manual corrections are recorded in an
audited ledger before the reports are recomputed.
"""

from __future__ import annotations

import threading
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from world_address_engine.gui.review_store import ReviewError, ReviewStore
from world_address_engine.io.reports import apply_review_corrections
from world_address_engine.jobs.runner import resume_job, run_job

MAX_REVIEW_ROWS = 5000


class JobWorker(QObject):
    """Runs a classification job off the GUI thread."""

    progress = Signal(int)
    message = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, *, resume: bool, job_dir: Path | None = None, **kwargs):
        super().__init__()
        self._resume = resume
        self._job_dir = job_dir
        self._kwargs = kwargs
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        """Ask the running job to stop at the next committed batch."""
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        try:
            if self._resume:
                report = resume_job(self._job_dir, verify_shards=True,
                                    cancel=self._cancel.is_set,
                                    progress=self.progress.emit)
            else:
                report = run_job(cancel=self._cancel.is_set,
                                 progress=self.progress.emit, **self._kwargs)
            self.finished.emit(report)
        except Exception as exc:  # surfaced in the window, never swallowed
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class MainWindow(QMainWindow):
    """The operator window: import, classify, review, export."""

    jobFinished = Signal()
    jobFailed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('World Address Sorting Engine - offline')
        self.resize(1180, 820)
        self._thread = None
        self._worker = None
        self._review_store = None
        self._rows = []
        self._output_dir = None
        self._meta = {}
        self._approved = {}
        self._job_state = 'idle'
        self._job_error = ''
        self._last_report = None
        self._dialogs = []
        self._build()

    def _build(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.addWidget(self._build_input())
        outer.addWidget(self._build_controls())
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_results())
        splitter.addWidget(self._build_review())
        outer.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage('Ready. Nothing has been read from disk yet.')

    def _build_input(self) -> QGroupBox:
        box = QGroupBox('Input and reference data')
        form = QFormLayout(box)
        row = QHBoxLayout()
        self.input_path = QLineEdit()
        browse = QPushButton('Choose file...')
        browse.clicked.connect(self._choose_input)
        row.addWidget(self.input_path, 1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow('Address file', holder)
        self.output_dir = QLineEdit()
        self.output_dir.setPlaceholderText(
            'Defaults to <input file>-classified next to the input')
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_dir, 1)
        out_browse = QPushButton('Choose folder...')
        out_browse.clicked.connect(self._choose_output_dir)
        out_row.addWidget(out_browse)
        out_holder = QWidget()
        out_holder.setLayout(out_row)
        form.addRow('Output folder', out_holder)
        self.encoding = QComboBox()
        self.encoding.addItems(['utf-8-sig', 'utf-8', 'big5', 'gb18030', 'cp1252'])
        form.addRow('Encoding', self.encoding)
        self.sheet_name = QLineEdit()
        form.addRow('Worksheet (XLSX only)', self.sheet_name)
        self.address_columns = QListWidget()
        self.address_columns.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.address_columns.setMaximumHeight(90)
        form.addRow('Address columns', self.address_columns)
        self.record_id_column = QLineEdit()
        form.addRow('Record id column (optional)', self.record_id_column)
        self.geo_db = QLineEdit()
        geo_row = QHBoxLayout()
        geo_row.addWidget(self.geo_db, 1)
        geo_browse = QPushButton('Choose pack...')
        geo_browse.clicked.connect(self._choose_geo_db)
        geo_row.addWidget(geo_browse)
        geo_holder = QWidget()
        geo_holder.setLayout(geo_row)
        form.addRow('GeoNames reference pack', geo_holder)
        self.hkp_db = QLineEdit()
        form.addRow('HKP destination catalogue', self.hkp_db)
        self.approval_manifest = QLineEdit()
        form.addRow('Signed approval manifest', self.approval_manifest)
        self.approval_key = QLineEdit()
        form.addRow('Approval key (keep outside the repository)', self.approval_key)
        self.test_only = QCheckBox('Mark the output TEST ONLY (no production postal use)')
        self.test_only.setChecked(True)
        form.addRow('Data class', self.test_only)
        return box

    def _build_controls(self) -> QGroupBox:
        box = QGroupBox('Job')
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.run_button = QPushButton('Classify')
        self.run_button.clicked.connect(self.start_job)
        self.resume_button = QPushButton('Resume')
        self.resume_button.clicked.connect(self.resume_job)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_job)
        self.progress = QProgressBar()
        row.addWidget(self.run_button)
        row.addWidget(self.resume_button)
        row.addWidget(self.cancel_button)
        row.addWidget(self.progress, 1)
        layout.addLayout(row)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        layout.addWidget(self.log)
        return box

    def _build_results(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel('Destination counts and review cases'))
        self.counts = QTableWidget(0, 2)
        self.counts.setHorizontalHeaderLabels(['HKP code', 'Count'])
        self.counts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.counts)
        self.review_table = QTableWidget(0, 5)
        self.review_table.setHorizontalHeaderLabels(
            ['Record', 'Status', 'Code', 'Reason', 'Address'])
        self.review_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.review_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.review_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.review_table, 1)
        self.source_versions = QLabel('No source versions loaded.')
        layout.addWidget(self.source_versions)
        return panel

    def _build_review(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel('Manual quality control'))
        self.operator = QLineEdit()
        self.operator.setPlaceholderText('Operator name')
        layout.addWidget(self.operator)
        self.review_reason = QLineEdit()
        self.review_reason.setPlaceholderText('Reason for the correction')
        layout.addWidget(self.review_reason)
        self.review_code = QComboBox()
        layout.addWidget(self.review_code)
        apply_button = QPushButton('Record correction')
        apply_button.clicked.connect(self.apply_review)
        layout.addWidget(apply_button)
        self.export_button = QPushButton('Write review log and refresh reports')
        self.export_button.clicked.connect(self.export_reviews)
        layout.addWidget(self.export_button)
        self.review_log = QTextEdit()
        self.review_log.setReadOnly(True)
        layout.addWidget(self.review_log, 1)
        return panel

    def _choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Choose the address file', '',
                                              'Address files (*.csv *.txt *.xlsx)')
        if path:
            self.input_path.setText(path)
            self._load_columns(Path(path))

    def _choose_geo_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Choose the reference pack', '',
                                              'SQLite packs (*.db *.sqlite)')
        if path:
            self.geo_db.setText(path)

    def _choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, 'Choose the output folder')
        if path:
            self.output_dir.setText(path)

    def _load_columns(self, path: Path) -> None:
        """Show the header row so the operator can pick the address columns."""
        import csv

        self.address_columns.clear()
        try:
            if path.suffix.lower() == '.xlsx':
                from openpyxl import load_workbook
                workbook = load_workbook(path, read_only=True)
                try:
                    sheet = self.sheet_name.text() or workbook.sheetnames[0]
                    worksheet = workbook[sheet]
                    header = next(worksheet.iter_rows(values_only=True), ())
                finally:
                    workbook.close()
            else:
                with path.open('r', encoding='utf-8-sig', newline='') as stream:
                    header = next(csv.reader(stream), ())
        except Exception as exc:
            self.log.append(f'Could not read the header: {exc}')
            return
        for name in header:
            if name:
                self.address_columns.addItem(str(name))
        for index in range(self.address_columns.count()):
            item = self.address_columns.item(index)
            if item.text().startswith('NAME_ADDRESS_LINE'):
                item.setSelected(True)

    def _selected_columns(self) -> tuple[str, ...]:
        return tuple(item.text() for item in self.address_columns.selectedItems())

    def start_job(self) -> None:
        source_text = self.input_path.text().strip()
        if not source_text:
            self._notify('Missing input', 'Choose an address file first.')
            return
        source = Path(source_text)
        if not source.is_file():
            self._notify('Missing input', f'{source.name} does not exist.')
            return
        options = {
            'encoding': self.encoding.currentText(),
            'address_columns': list(self._selected_columns()),
            'record_id_column': self.record_id_column.text() or None,
            'sheet_name': self.sheet_name.text() or None,
        }
        chosen = self.output_dir.text().strip()
        output_dir = Path(chosen) if chosen else source.parent / f'{source.stem}-classified'
        if (output_dir / 'Run_Manifest.json').exists():
            self._notify(
                'Output already holds a finished run',
                'A completed run is never overwritten. Choose another folder, '
                'or press Resume to continue the interrupted job.')
            return
        self._output_dir = output_dir
        self._review_store = None
        manifest = self.approval_manifest.text().strip()
        key = self.approval_key.text().strip()
        self._start(JobWorker(
            resume=False,
            input_path=source,
            output_dir=output_dir,
            geo_db=Path(self.geo_db.text()),
            hkp_db=Path(self.hkp_db.text()),
            input_options=options,
            batch_size=10000,
            allow_unverified_reference_data=self.test_only.isChecked(),
            approval_manifest=Path(manifest) if manifest else None,
            approval_key=Path(key) if key else None,
        ))

    def resume_job(self) -> None:
        if self._output_dir is None:
            self._notify('Nothing to resume', 'Run a job first.')
            return
        self._start(JobWorker(resume=True, job_dir=self._output_dir))

    def _start(self, worker: JobWorker) -> None:
        self._job_state = 'running'
        self._job_error = ''
        self.run_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def cancel_job(self) -> None:
        """Stop at the next committed batch; the checkpoint stays resumable."""
        if self._worker is not None:
            self._worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage('Cancelling after the current batch...')

    @Slot(int)
    def _on_progress(self, records: int) -> None:
        self.statusBar().showMessage(f'{records} records classified')

    @Slot(dict)
    def _on_finished(self, report: dict) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self._job_state = 'done'
        self._last_report = report
        self.run_button.setEnabled(True)
        self.resume_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.log.append(f'Finished: {report}')
        self._load_results()
        self.jobFinished.emit()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self._job_state = 'failed'
        self._job_error = message
        self.run_button.setEnabled(True)
        self.resume_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.log.append(f'Failed: {message}')
        self._notify('Job failed', message, critical=True)
        self.jobFailed.emit(message)

    def _notify(self, title: str, text: str, *, critical: bool = False) -> None:
        """Show a message without blocking the event loop.

        A modal dialog would freeze the window (and the worker) until the
        operator clicks it, so the notice is window-modal and non-blocking.
        """
        self.log.append(f'{title}: {text}')
        self.statusBar().showMessage(f'{title}: {text}', 20000)
        icon = QMessageBox.Critical if critical else QMessageBox.Warning
        box = QMessageBox(icon, title, text, QMessageBox.Ok, self)
        box.setWindowModality(Qt.WindowModality.NonModal)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.show()
        self._dialogs.append(box)

    @property
    def job_state(self) -> str:
        """``idle``, ``running``, ``done`` or ``failed``."""
        return self._job_state

    @property
    def worker_thread(self):
        """The thread the job runs on, or ``None`` before the first job."""
        return self._thread

    @property
    def approved_codes(self) -> dict[str, str]:
        """destination_id -> code, for the codes the approval ratifies."""
        return dict(self._approved)

    def _load_results(self) -> None:
        """Read the published export back for the operator to review."""
        import csv
        import json

        if self._output_dir is None:
            return
        detail = self._output_dir / 'Classified_Addresses.csv'
        if not detail.is_file():
            return
        from world_address_engine.io.reports import RESULT_FIELDS

        counts: dict[str, int] = {}
        review_rows: list[dict] = []
        with detail.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            original_fields = [name for name in (reader.fieldnames or [])
                               if name not in RESULT_FIELDS]
            for row in reader:
                code = row.get('HKP_Destination_Code', '')
                if code:
                    counts[code] = counts.get(code, 0) + 1
                elif len(review_rows) < MAX_REVIEW_ROWS:
                    review_rows.append(row)
        self.counts.setRowCount(len(counts))
        for index, (code, count) in enumerate(sorted(counts.items())):
            self.counts.setItem(index, 0, QTableWidgetItem(code))
            self.counts.setItem(index, 1, QTableWidgetItem(str(count)))
        self.review_table.setRowCount(len(review_rows))
        for index, row in enumerate(review_rows):
            values = [row.get('Source_Record_No', ''),
                      row.get('Classification_Status', ''),
                      row.get('HKP_Destination_Code', ''),
                      row.get('Review_Reason', ''),
                      ' | '.join(str(row.get(name, '')).strip()
                                 for name in original_fields
                                 if str(row.get(name, '')).strip())]
            for column, value in enumerate(values):
                self.review_table.setItem(index, column, QTableWidgetItem(str(value)))
        self._rows = review_rows
        manifest = self._output_dir / 'Run_Manifest.json'
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding='utf-8'))
            meta = data.get('run_metadata', {})
            self._meta = meta
            self.source_versions.setText(
                f"Data class: {data.get('data_class')} | catalogue "
                f"{meta.get('catalogue_version')} | packs {meta.get('geo_pack_versions')} "
                f"| rules {meta.get('rules_version')}")
        self._load_approved_codes()

    def _load_approved_codes(self) -> None:
        """List only the destination codes the signed approval allows.

        The operator may never assert a code the release process has not
        ratified, so the panel is fed from the approval, not from the data
        file's own `approval_status` column.
        """
        self.review_code.clear()
        path = self.hkp_db.text().strip()
        if not path:
            return
        try:
            from world_address_engine.hkp.catalogue import approved_codes
            approval = self._load_approval(Path(path))
            if approval is None:
                self._approved = {}
                self.log.append(
                    'No signed approval was supplied, so no destination code '
                    'may be asserted.')
                return
            codes = approved_codes(Path(path), approval)
        except Exception as exc:
            self._approved = {}
            self.log.append(f'No approved catalogue is available for review: {exc}')
            return
        self._approved = codes
        for code in sorted(set(codes.values())):
            self.review_code.addItem(code)

    def _load_approval(self, db_path: Path):
        """Verify the signed approval when the operator supplied one."""
        manifest = self.approval_manifest.text().strip()
        key = self.approval_key.text().strip()
        if not manifest or not key:
            return None
        from world_address_engine.hkp.approval import load_approval
        return load_approval(Path(manifest), Path(key), db_path)

    def apply_review(self) -> None:
        """Record one audited correction for the selected review row."""
        selected = self.review_table.selectionModel().selectedRows()
        if not selected:
            self._notify('No selection', 'Select a review row first.')
            return
        index = selected[0].row()
        if index >= len(self._rows):
            return
        row = self._rows[index]
        code = self.review_code.currentText() or None
        if self._review_store is None:
            ledger = (self._output_dir or Path.cwd()) / 'review_decisions.jsonl'
            self._review_store = ReviewStore(ledger, operator=self.operator.text(),
                                             catalogue_version=self._meta.get(
                                                 'catalogue_version', ''),
                                             geo_pack_versions=self._meta.get(
                                                 'geo_pack_versions', ''))
        else:
            self._review_store.operator = self.operator.text()
        try:
            decision = self._review_store.decide(
                int(row.get('Source_Record_No', 0) or 0),
                record_id=row.get('Record_ID', ''),
                original_status=row.get('Classification_Status', ''),
                original_code=row.get('HKP_Destination_Code') or None,
                original_reason=row.get('Review_Reason', ''),
                new_code=code,
                reason=self.review_reason.text(),
                approved_codes=self._approved or None,
            )
        except ReviewError as exc:
            self._notify('Correction rejected', str(exc))
            return
        self.review_log.append(
            f'record {decision.record_no}: {decision.original_status} -> '
            f'{decision.new_status} {decision.new_code or ""} ({decision.reason})')

    def export_reviews(self) -> None:
        """Refresh the reports so the correction is reflected in the counts."""
        if self._review_store is None or self._output_dir is None:
            self._notify('Nothing to export', 'No corrections yet.')
            return
        self._review_store.write_csv(self._output_dir / 'Review_Corrections.csv')
        counts = apply_review_corrections(self._output_dir, self._review_store.decisions())
        self.log.append(f'Reports refreshed: {counts}')
        self._load_results()

    def closeEvent(self, event) -> None:
        """Never leave a worker thread running behind a closed window."""
        thread = self._thread
        if thread is not None and thread.isRunning():
            self._worker.request_cancel()
            thread.quit()
            thread.wait(5000)
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication(argv if argv is not None else sys.argv[:1])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
