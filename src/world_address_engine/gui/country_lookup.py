"""Persistent, private lookup session owned entirely by its background thread."""
from pathlib import Path
import json
import threading
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QApplication


def _source_stamp(config):
    paths = []
    for value in config[:2]:
        if value:
            path = Path(value)
            paths.extend((path, path.with_name('manifest.json'), path.with_name('quarantine.jsonl')))
    return tuple((str(p), (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                  if p.is_file() else None) for p in paths)


class LookupUnavailable(ValueError):
    """Fixed, address-free feedback that is safe to show in the UI."""


class LookupSession:
    def __init__(self, config):
        from world_address_engine.data.pack_registry import verify_pack, require_readable_pack
        from world_address_engine.data.hk_regional import hk_pack_metadata
        from world_address_engine.data.country_codes import load_country_codes
        from world_address_engine.data.zone_mappings import load_zone_mappings
        from world_address_engine.matching.country import CountryClassifier
        geo, hk = config[:2]
        hk_enabled = config[2] if len(config) > 2 else bool(hk)
        if hk_enabled and (not hk or not Path(hk).is_file()):
            raise LookupUnavailable('Hong Kong pack is enabled but missing. Choose an installed pack or explicitly turn it off.')
        if not geo:
            raise LookupUnavailable('Missing GeoNames pack. Choose an installed global pack.')
        path = Path(geo)
        verify_pack(path, path.with_name('manifest.json'))
        require_readable_pack(path)
        manifest = json.loads(path.with_name('manifest.json').read_text(encoding='utf8'))
        if manifest['profile'] not in ('COMPACT_GLOBAL', 'EXTENDED_GLOBAL'):
            raise ValueError('Choose a global GeoNames pack')
        regional = hk_pack_metadata(Path(hk)) if hk else None
        self.catalogue = load_country_codes()
        self.zones = load_zone_mappings()
        self.model = CountryClassifier(path, self.catalogue, hk_regional_db=Path(hk) if hk else None)
        # Model construction and the initial readonly connection belong to this thread.
        try:
            self.lookup('')
        except Exception:
            self.model.close()
            raise
        hk_status = regional.get('version', 'unknown') if regional else 'disabled'
        coverage = regional.get('source_validation', {}) if regional else {}
        if coverage.get('coverage') == 'partial':
            hk_status += f" (partial coverage; {coverage['quarantined_feature_count']} excluded)"
        self.status = f"GeoNames: {manifest['pack_version']} | Hong Kong: {hk_status} | Zones: {self.zones.version}"

    def lookup(self, text):
        from world_address_engine.models import AddressRecord
        from world_address_engine.data.zone_mappings import zone_values
        from world_address_engine.gui.country_cases import REASONS
        try:
            inference = self.model.classify(AddressRecord(1, '', None, None, {}, text, None))
            code = inference.country_code or ''
            entry = self.catalogue.entries.get(code)
            zone, novsn = zone_values(code, self.zones)
            return {'code': code, 'name': f'{entry.name_en} / {entry.name_tc}' if entry else '',
                    'status': inference.status, 'zone': zone, 'novsn': novsn,
                    'reason': REASONS.get(inference.reason, inference.reason)}
        finally:
            # Keep the verified model and connections, never query history.
            self.model._cache.clear()
            self.model._cache_text_bytes = 0

    def close(self):
        self.model.close()


class LookupThread(QThread):
    state = Signal(int, bool, str)
    result = Signal(int, object)
    settled = Signal(int)

    def __init__(self):
        super().__init__()
        self._condition = threading.Condition()
        self._pending = None
        self._stop = False

    def submit(self, generation, config, text=None):
        with self._condition:
            self._pending = (generation, config, text)
            self._condition.notify()

    def request_cancel(self):
        self.shutdown()

    def shutdown(self):
        with self._condition:
            self._stop = True
            self._pending = None
            self._condition.notify()

    def run(self):
        session, active, stamp = None, None, None
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._stop or self._pending is not None)
                    if self._stop:
                        return
                    generation, config, text = self._pending
                    self._pending = None
                try:
                    current = _source_stamp(config)
                    if session is None or active != config or stamp != current:
                        if session is not None:
                            session.close()
                            session = None
                        self.state.emit(generation, False, 'Verifying installed packs and loading lookup model…')
                        session = LookupSession(config)
                        if _source_stamp(config) != current:
                            session.close()
                            session = None
                            raise ValueError('Reference pack changed during verification')
                        active, stamp = config, current
                    self.state.emit(generation, True, session.status)
                    if text is not None:
                        payload = session.lookup(text)
                        if _source_stamp(config) != stamp:
                            raise ValueError('Reference pack changed during lookup')
                        self.result.emit(generation, payload)
                except LookupUnavailable as exc:
                    self.state.emit(generation, False, str(exc))
                except Exception:
                    # Never include classifier exception text: it could contain the input.
                    self.state.emit(generation, False, 'Lookup unavailable: missing, invalid or changed offline pack. Check reference settings and retry.')
                finally:
                    text = None
                    self.settled.emit(generation)
        finally:
            if session is not None:
                session.close()


class QuickLookupPanel(QWidget):
    queryRequested = Signal()
    edited = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel('Single address (local display only; no history or files)')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.address = QPlainTextEdit()
        self.address.setAccessibleName('Single address, multiple lines')
        label.setBuddy(self.address)
        self.address.setPlaceholderText('Enter one address. Enter adds a line; Ctrl+Enter queries.')
        layout.addWidget(self.address, 1)
        row = QHBoxLayout()
        self.query = QPushButton('Query (Ctrl+Enter)')
        self.clear = QPushButton('Clear')
        self.copy = QPushButton('Copy code')
        for button in (self.query, self.clear, self.copy):
            row.addWidget(button)
        layout.addLayout(row)
        self.result = QLabel('')
        self.result.setWordWrap(True)
        self.result.setTextFormat(Qt.TextFormat.PlainText)
        self.result.setAccessibleName('Country, name, status, Zone and NOVSN')
        layout.addWidget(self.result)
        self.status = QLabel('Waiting to verify installed reference packs…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._code = ''
        self.query.setEnabled(False)
        self.copy.setEnabled(False)
        self.query.clicked.connect(self.queryRequested)
        self.clear.clicked.connect(self.address.clear)
        self.address.textChanged.connect(self.invalidate)
        self.copy.clicked.connect(self.copy_code)
        self.shortcut = QShortcut(QKeySequence('Ctrl+Return'), self)
        self.shortcut.activated.connect(self.query.click)
        self.keypad_shortcut = QShortcut(QKeySequence('Ctrl+Enter'), self)
        self.keypad_shortcut.activated.connect(self.query.click)

    def copy_code(self):
        if self._code:
            QApplication.clipboard().setText(self._code)

    def invalidate(self):
        self._code = ''
        self.copy.setEnabled(False)
        self.result.clear()
        self.edited.emit()

    def show_result(self, payload):
        self._code = payload['code']
        self.result.setText(f"Country: {payload['code'] or 'unassigned'} | {payload['name']}\nStatus: {payload['status']}\nZone: {payload['zone']} | NOVSN: {payload['novsn']}\nReason: {payload.get('reason', '')}")
        self.copy.setEnabled(bool(self._code))
