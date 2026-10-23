"""Offline PySide6 desktop workflow for the address classifier.

The GUI is a thin shell around the same deterministic engine the CLI uses.
Widgets never touch SQL or the network: the job runs in a worker thread so
the window stays responsive, and manual corrections are recorded in an
audited ledger before the reports are recomputed.

Two rules shape the review panel:

* it is bound to the approval that authorised the *run*, never to whatever
  the operator currently has typed into a text box, and
* every long file operation runs off the GUI thread, so a multi-million row
  export never freezes the window.
"""

from __future__ import annotations

import atexit
import threading
import sys
import time
from functools import partial
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QThread, Signal, Slot
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
CLOSE_GRACE_SECONDS = 15.0

# Every worker thread is kept alive here until it has really ended. A
# QThread that is garbage collected while it still runs aborts the whole
# interpreter (0xC0000409), which used to kill the test run whenever a
# GUI test failed while a job was in flight.
_LIVE_THREADS: set = set()


class WorkerThread(QThread):
    """Runs one callable on a worker thread and reports the outcome.

    A plain ``QThread`` subclass is deliberate: the thread owns no event
    loop, so it ends as soon as the work is done. Nothing can then destroy
    a still-running thread together with the window, which is what used to
    abort the interpreter (0xC0000409) when a GUI test failed mid-job.
    """

    progressed = Signal(int)
    detailedProgress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, func: Callable[[Callable[[int], None]], object],
                 cancel: threading.Event | None = None, *, detailed: bool = False):
        super().__init__()
        self._func = func
        self._cancel = cancel
        self._detailed = detailed
        self.thread_ident: int | None = None

    def request_cancel(self) -> None:
        """Ask the work to stop at its next checkpoint."""
        if self._cancel is not None:
            self._cancel.set()

    def run(self) -> None:
        self.thread_ident = threading.get_ident()
        try:
            if self._detailed:
                result = self._func(self.progressed.emit, self.detailedProgress.emit)
            else:
                result = self._func(self.progressed.emit)
            self.succeeded.emit(result)
        except Exception as exc:  # surfaced in the window, never swallowed
            self.failed.emit(f'{type(exc).__name__}: {exc}')


def _thread_finished(thread: WorkerThread) -> None:
    """Release a finished worker so its Qt object can be reclaimed."""
    _LIVE_THREADS.discard(thread)


@atexit.register
def _shutdown_live_threads() -> None:
    """Never leave a running worker behind when the interpreter exits.

    A QThread that is destroyed while it still runs aborts the process
    (0xC0000409), so the workers are asked to stop and joined here.
    """
    for thread in list(_LIVE_THREADS):
        try:
            thread.request_cancel()
            thread.wait(15000)
        except Exception:  # pragma: no cover - best effort at shutdown
            pass


def _read_published_export(output_dir: Path) -> dict:
    """Read the published export back. Runs off the GUI thread.

    A module level function on purpose: a worker closure that captured the
    window would keep the whole window (and its thread) alive in a
    reference cycle, and a thread collected while it still runs aborts the
    interpreter.
    """
    import csv
    import json

    from world_address_engine.io.reports import RESULT_FIELDS

    counts: dict[str, int] = {}
    review_rows: list[dict] = []
    review_total = 0
    original_fields: list[str] = []
    detail = output_dir / 'Classified_Addresses.csv'
    if detail.is_file():
        with detail.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            original_fields = [name for name in (reader.fieldnames or [])
                               if name not in RESULT_FIELDS]
            for row in reader:
                code = row.get('HKP_Destination_Code', '')
                if code:
                    counts[code] = counts.get(code, 0) + 1
                else:
                    review_total += 1
                    if len(review_rows) < MAX_REVIEW_ROWS:
                        review_rows.append(row)
    meta: dict = {}
    data_class = ''
    manifest = output_dir / 'Run_Manifest.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        meta = data.get('run_metadata', {}) or {}
        data_class = str(data.get('data_class') or '')
    return {'counts': counts, 'review_rows': review_rows,
            'review_total': review_total, 'meta': meta,
            'data_class': data_class, 'original_fields': original_fields}


class MainWindow(QMainWindow):
    """The operator window: import, classify, review, export."""

    jobFinished = Signal()
    jobFailed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('World Address Sorting Engine - offline')
        self.resize(1180, 820)
        self._thread = None
        self._cancel = threading.Event()
        self._on_success = None
        self._on_error = None
        self._on_finished = None
        self._last_result = None
        self._last_error = ''
        self._review_store = None
        self._rows = []
        self._output_dir = None
        self._meta = {}
        self._approved = {}
        self._approved_destinations = {}
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
        self.review_summary = QLabel('No run loaded.')
        layout.addWidget(self.review_summary)
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
        encoding = self.encoding.currentText() or 'utf-8-sig'
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
                with path.open('r', encoding=encoding, newline='') as stream:
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

    # ------------------------------------------------------------------
    # worker plumbing
    # ------------------------------------------------------------------

    def _start_worker(self, func, *, on_success=None, on_error=None,
                      on_finished=None) -> bool:
        """Run ``func`` off the GUI thread.

        Only one worker runs at a time and the next stage is started from
        the thread's ``finished`` signal, so a follow-up never races the
        previous worker.
        """
        if self._thread is not None and self._thread.isRunning():
            self._notify('Busy', 'The previous operation is still running.')
            return False
        thread = WorkerThread(func, cancel=self._cancel)
        thread.progressed.connect(self._on_progress)
        thread.succeeded.connect(self._on_worker_succeeded)
        thread.failed.connect(self._on_worker_failed)
        thread.finished.connect(self._on_worker_finished)
        thread.finished.connect(partial(_thread_finished, thread))
        self._thread = thread
        self._on_success = on_success
        self._on_error = on_error
        self._on_finished = on_finished
        _LIVE_THREADS.add(thread)
        thread.start()
        return True

    @Slot(object)
    def _on_worker_succeeded(self, result):
        self._last_result = result
        if self._on_success is not None:
            self._on_success(result)

    @Slot(str)
    def _on_worker_failed(self, message):
        self._last_error = message
        if self._on_error is not None:
            self._on_error(message)

    @Slot()
    def _on_worker_finished(self):
        callback = self._on_finished
        # Bound callbacks otherwise retain the closed window in a cycle,
        # which a later worker can collect away from the GUI thread.
        self._on_success = None
        self._on_error = None
        self._on_finished = None
        if callback is not None:
            callback()

    # ------------------------------------------------------------------
    # jobs
    # ------------------------------------------------------------------

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
        geo_db = Path(self.geo_db.text().strip())
        hkp_db = Path(self.hkp_db.text().strip())
        cancel = self._cancel
        test_only = self.test_only.isChecked()
        self._cancel.clear()
        self._job_state = 'running'
        self._job_error = ''
        self.run_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)

        def work(emit):
            return run_job(cancel=cancel.is_set, progress=emit,
                           input_path=source, output_dir=output_dir,
                           geo_db=geo_db, hkp_db=hkp_db, input_options=options,
                           batch_size=10000,
                           allow_unverified_reference_data=test_only,
                           approval_manifest=Path(manifest) if manifest else None,
                           approval_key=Path(key) if key else None)

        self._start_worker(work, on_success=self._on_job_done,
                           on_error=self._on_job_failed,
                           on_finished=self._after_job)

    def resume_job(self) -> None:
        if self._output_dir is None:
            self._notify('Nothing to resume', 'Run a job first.')
            return
        output_dir = self._output_dir
        cancel = self._cancel
        self._cancel.clear()
        self._job_state = 'running'
        self._job_error = ''
        self.run_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)

        def work(emit):
            return resume_job(output_dir, verify_shards=True,
                              cancel=cancel.is_set, progress=emit)

        self._start_worker(work, on_success=self._on_job_done,
                           on_error=self._on_job_failed,
                           on_finished=self._after_job)

    def cancel_job(self) -> None:
        """Stop at the next committed batch; the checkpoint stays resumable."""
        self._cancel.set()
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage('Cancelling after the current batch...')

    @Slot(int)
    def _on_progress(self, records: int) -> None:
        self.statusBar().showMessage(f'{records} records classified')

    def _on_job_done(self, report: dict) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        cancelled = report.get('run_status') == 'CANCELLED'
        # The run is only "done" once the export has been read back into
        # the window, so the operator never sees an empty table next to a
        # finished job.
        self._job_state = 'cancelled' if cancelled else 'loading'
        self._last_report = report
        self.run_button.setEnabled(True)
        self.resume_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.log.append(f'Finished: {report}')
        if cancelled:
            self.statusBar().showMessage('Cancelled. The checkpoint can be resumed.')

    def _after_job(self) -> None:
        """Start the read-back once the worker thread has really ended."""
        if self._job_state == 'loading':
            self._load_results()

    def _on_job_failed(self, message: str) -> None:
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
        """``idle``, ``running``, ``done``, ``cancelled`` or ``failed``."""
        return self._job_state

    @property
    def worker_thread(self):
        """The thread the last operation ran on, or ``None``."""
        return self._thread

    @property
    def busy(self) -> bool:
        """True while a worker thread is still running."""
        thread = self._thread
        if thread is None:
            return False
        try:
            return thread.isRunning()
        except RuntimeError:  # the Qt object was already reclaimed
            return False

    @property
    def worker_thread_ident(self):
        """The OS thread id the worker really ran on."""
        return getattr(self._thread, 'thread_ident', None)

    @property
    def approved_codes(self) -> dict[str, str]:
        """destination_id -> code, for the codes the run's approval ratifies."""
        return dict(self._approved)

    # ------------------------------------------------------------------
    # reading the published export
    # ------------------------------------------------------------------

    def _load_results(self) -> None:
        """Read the published export back for the operator to review.

        The file can hold millions of rows, so the read runs off the GUI
        thread and only the finished summary is applied to the widgets.
        """
        if self._output_dir is None:
            return
        output_dir = self._output_dir

        def work(_emit):
            return _read_published_export(output_dir)

        self._start_worker(work, on_success=self._apply_results,
                           on_error=self._on_background_error)

    def _apply_results(self, payload: dict) -> None:
        self._meta = payload.get('meta', {}) or {}
        self._rows = payload.get('review_rows', [])
        counts = payload.get('counts', {})
        self.counts.setRowCount(len(counts))
        for index, (code, count) in enumerate(sorted(counts.items())):
            self.counts.setItem(index, 0, QTableWidgetItem(code))
            self.counts.setItem(index, 1, QTableWidgetItem(str(count)))
        original_fields = payload.get('original_fields', [])
        rows = self._rows
        self.review_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [row.get('Source_Record_No', ''),
                      row.get('Classification_Status', ''),
                      row.get('HKP_Destination_Code', ''),
                      row.get('Review_Reason', ''),
                      ' | '.join(str(row.get(name, '')).strip()
                                 for name in original_fields
                                 if str(row.get(name, '')).strip())]
            for column, value in enumerate(values):
                self.review_table.setItem(index, column, QTableWidgetItem(str(value)))
        total = int(payload.get('review_total', len(rows)))
        shown = len(rows)
        if total > shown:
            self.review_summary.setText(
                f'{total} records need review; showing the first {shown}.')
        else:
            self.review_summary.setText(f'{total} records need review.')
        self.source_versions.setText(
            f"Data class: {payload.get('data_class')} | catalogue "
            f"{self._meta.get('catalogue_version')} | packs "
            f"{self._meta.get('geo_pack_versions')} | rules "
            f"{self._meta.get('rules_version')}")
        self._load_approved_codes()
        if self._job_state == 'loading':
            self._job_state = 'done'
            self.jobFinished.emit()

    def _on_background_error(self, message: str) -> None:
        self.log.append(f'Background operation failed: {message}')
        self._notify('Operation failed', message, critical=True)

    # ------------------------------------------------------------------
    # the review panel
    # ------------------------------------------------------------------

    def _run_approval(self):
        """The approval that authorised this run, or ``None`` with a reason.

        The panel is bound to the *run*: the run manifest names the approval
        manifest and pins its digest, the digest is verified, and the
        operator's key is used only to check that exact manifest's
        signature. What the operator has typed into the approval text box
        never decides which codes may be asserted.
        """
        from world_address_engine.hkp.approval import file_sha256

        meta = self._meta or {}
        path = meta.get('approval_manifest_path')
        digest = meta.get('approval_manifest_sha256')
        if not path or not digest:
            return None, ('This run recorded no signed approval, so no '
                          'destination code may be asserted.')
        manifest_path = Path(path)
        if not manifest_path.is_file():
            return None, 'The approval manifest recorded by the run is missing.'
        if file_sha256(manifest_path) != digest:
            return None, ('The approval manifest no longer matches the digest '
                          'recorded by the run.')
        key = self.approval_key.text().strip()
        if not key:
            return None, ('No approval key was supplied, so the run approval '
                          'cannot be verified.')
        db_text = self.hkp_db.text().strip()
        if not db_text:
            return None, 'The HKP catalogue recorded by the run is missing.'
        db = Path(db_text)
        expected = meta.get('hkp_sha256')
        if expected and file_sha256(db) != expected:
            return None, 'The HKP catalogue no longer matches the run.'
        try:
            from world_address_engine.hkp.approval import load_approval
            return load_approval(manifest_path, Path(key), db), ''
        except Exception as exc:
            return None, f'The run approval could not be verified: {exc}'

    def _load_approved_codes(self) -> None:
        """List only the destination codes the run's approval ratifies."""
        self.review_code.clear()
        self._approved = {}
        self._approved_destinations = {}
        approval, problem = self._run_approval()
        if approval is None:
            self.log.append(problem)
            return
        db = Path(self.hkp_db.text().strip())
        try:
            from world_address_engine.hkp.catalogue import (
                approved_codes, approved_destinations)
            self._approved = approved_codes(db, approval)
            self._approved_destinations = approved_destinations(db, approval)
        except Exception as exc:
            self._approved = {}
            self._approved_destinations = {}
            self.log.append(f'No approved catalogue is available for review: {exc}')
            return
        for code in sorted(set(self._approved.values())):
            self.review_code.addItem(code)

    def _store(self) -> ReviewStore:
        """The ledger for this run, carrying the run's own provenance."""
        if self._review_store is None:
            ledger = (self._output_dir or Path.cwd()) / 'review_decisions.jsonl'
            self._review_store = ReviewStore(
                ledger, operator=self.operator.text(),
                catalogue_version=self._meta.get('catalogue_version', ''),
                geo_pack_versions=self._meta.get('geo_pack_versions', ''),
                rules_version=self._meta.get('rules_version', ''),
                approval_id=self._meta.get('approval_id', '') or '',
                approval_manifest_sha256=(
                    self._meta.get('approval_manifest_sha256', '') or ''))
        else:
            self._review_store.operator = self.operator.text()
        return self._review_store

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
        try:
            record_no = int(row.get('Source_Record_No', 0) or 0)
        except (TypeError, ValueError):
            self._notify('Correction rejected', 'The row has no record number.')
            return
        store = self._store()
        try:
            decision = store.decide(
                record_no,
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
        output_dir = self._output_dir
        try:
            self._review_store.write_csv(output_dir / 'Review_Corrections.csv')
        except OSError as exc:
            self._notify('Review log not written', str(exc), critical=True)
            return
        decisions = self._review_store.decisions()
        approved = dict(self._approved_destinations)

        def work(_emit):
            return apply_review_corrections(
                output_dir, decisions,
                approved_destination=approved.get,
                require_validated_codes=True)

        def done(counts):
            self.log.append(f'Reports refreshed: {counts}')

        self._start_worker(work, on_success=done,
                           on_error=self._on_background_error,
                           on_finished=self._load_results)

    def closeEvent(self, event) -> None:
        """Never leave a worker thread running behind a closed window."""
        thread = self._thread
        if thread is not None and thread.isRunning():
            self._cancel.set()
            deadline = time.monotonic() + CLOSE_GRACE_SECONDS
            while thread.isRunning() and time.monotonic() < deadline:
                thread.wait(100)
            if thread.isRunning():
                event.ignore()
                self._notify(
                    'Still running',
                    'The job is still running. Wait for it to finish or cancel '
                    'it before closing the window.')
                return
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication
    from world_address_engine.gui.country_app import CountryAnalysisWindow

    app = QApplication(argv if argv is not None else sys.argv[:1])
    window = CountryAnalysisWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
