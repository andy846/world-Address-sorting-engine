"""Optional regional GUI contracts with synthetic inputs only."""
import gc
import json
from pathlib import Path
import threading
import weakref

import pytest

from tests.integration.test_country_gui import (  # noqa: F401
    app, window, configure, install_runner, report, wait,
)


def test_discovery_prefills_without_enabling(tmp_path, monkeypatch, app):
    from world_address_engine.gui.country_app import CountryAnalysisWindow
    monkeypatch.chdir(tmp_path)
    for version in ('2026-01', '2026-02'):
        folder = tmp_path / 'packs' / f'hk-bilingual-als-{version}'
        folder.mkdir(parents=True)
        (folder / 'pack.db').touch()
    instance = CountryAnalysisWindow()
    try:
        assert instance.hk_regional_db.text() == str(folder / 'pack.db')
        assert not instance.hk_enabled.isChecked()
        assert instance.hk_enabled.accessibleName()
        assert instance.hk_regional_db.accessibleName()
    finally:
        instance.close()


@pytest.mark.parametrize('enabled', [False, True])
def test_optional_kwarg_runs_only_when_enabled(window, tmp_path, app, monkeypatch, enabled):
    configure(window, tmp_path)
    path = tmp_path / 'regional.db'
    window.hk_regional_db.setText(str(path))
    window.hk_enabled.setChecked(enabled)
    main_thread = threading.get_ident()
    calls = []

    def analyze(*args, **kwargs):
        assert threading.get_ident() != main_thread
        calls.append(kwargs)
        return report('PAUSED')

    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'paused', window.log.toPlainText()
    assert len(calls) == 1
    if enabled:
        assert calls[0]['hk_regional_db'] == path
    else:
        assert 'hk_regional_db' not in calls[0]


def test_browse_enables_but_cancel_does_not(window, monkeypatch):
    from world_address_engine.gui.country_app import QFileDialog
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: ('chosen.db', ''))
    window._choose_hk_db()
    assert window.hk_enabled.isChecked()
    assert window.hk_regional_db.text() == 'chosen.db'
    window.hk_enabled.setChecked(False)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: ('', ''))
    window._choose_hk_db()
    assert not window.hk_enabled.isChecked()


@pytest.mark.parametrize('path', ['', 'missing.db'])
def test_selected_path_failure_on_worker_is_clear_without_state(window, tmp_path, app, monkeypatch, path):
    configure(window, tmp_path)
    window.hk_enabled.setChecked(True)
    window.hk_regional_db.setText(path)
    main_thread = threading.get_ident()

    def analyze(*args, **kwargs):
        assert threading.get_ident() != main_thread
        assert kwargs['hk_regional_db'] is not None
        raise ValueError('Hong Kong regional pack is missing or invalid')

    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed'
    assert 'Hong Kong' in window.log.toPlainText()
    assert not (tmp_path / 'export').exists()
    assert window.hk_enabled.isEnabled()


@pytest.mark.parametrize('metadata,expected', [(None, 'disabled'), ({'version': 'official-test-v1'}, 'official-test-v1')])
def test_resume_uses_pins_and_displays_report_version(window, tmp_path, app, monkeypatch, metadata, expected):
    configure(window, tmp_path)
    window.hk_enabled.setChecked(True)
    window.hk_regional_db.setText('different-current-choice.db')
    calls = []

    def resume(output, **kwargs):
        calls.append(kwargs)
        result = report('PAUSED')
        result['run_metadata']['hk_regional'] = metadata
        return result

    install_runner(monkeypatch, lambda *a, **k: pytest.fail('new run'), resume)
    window.resume_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'paused'
    assert 'hk_regional_db' not in calls[0]
    assert expected in window.source_versions.text()
    assert 'different-current-choice' not in window.source_versions.text()


def test_hk_hashing_stage_and_reason_are_human_readable(window):
    from world_address_engine.gui.country_cases import REASONS
    window._on_stage_event({'stage': 'hashing_hk_pack', 'processed': 0})
    assert 'Hong Kong' in window.activity.text()
    assert 'fingerprint' in window.activity.text()
    assert 'Hong Kong' in REASONS['HK_REGIONAL_ADDRESS_MATCH']


def test_optional_controls_do_not_retain_closed_window(app, tmp_path, monkeypatch):
    from world_address_engine.gui.country_app import CountryAnalysisWindow
    monkeypatch.chdir(tmp_path)
    enabled = gc.isenabled()
    gc.disable()
    try:
        instance = CountryAnalysisWindow()
        instance.hk_enabled.setChecked(True)
        instance.close()
        ref = weakref.ref(instance)
        del instance
        app.processEvents()
        assert ref() is None
    finally:
        if enabled:
            gc.enable()


@pytest.mark.parametrize('invalid', ['missing', 'wrong_profile'])
def test_real_worker_rejects_invalid_pack_before_state(window, app, tmp_path, invalid):
    from tests.unit.test_retrieve import geo
    configure(window, tmp_path)
    global_db = geo(tmp_path)
    window.geo_db.setText(str(global_db))
    window.hk_enabled.setChecked(True)
    window.hk_regional_db.setText(str(global_db if invalid == 'wrong_profile' else tmp_path / 'missing.db'))
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed', window.log.toPlainText()
    assert 'Hong Kong' in window._last_error
    assert not (tmp_path / 'export').exists()


@pytest.mark.parametrize('enabled', [False, True])
def test_real_worker_report_and_disabled_outputs_match_direct_runner(window, app, tmp_path, monkeypatch, enabled):
    from tests.unit.test_retrieve import geo
    from tests.unit.test_hk_als_builder import build
    from world_address_engine.jobs.country_analysis import analyze_job
    configure(window, tmp_path)
    global_db = geo(tmp_path)
    regional_root = tmp_path / 'hk'
    regional_root.mkdir()
    build(regional_root)
    hk = regional_root / 'pack' / 'pack.db'
    window.geo_db.setText(str(global_db))
    window.hk_regional_db.setText(str(hk))
    window.hk_enabled.setChecked(enabled)
    direct = tmp_path / 'direct'
    analyze_job(tmp_path / 'synthetic.csv', direct, global_db,
                window._input_options(), **({'hk_regional_db': hk} if enabled else {}))
    from world_address_engine.jobs import country_analysis
    original_metadata = country_analysis.hk_pack_metadata
    validation_threads = []
    main_thread = threading.get_ident()

    def metadata(path):
        validation_threads.append(threading.get_ident())
        return original_metadata(path)

    monkeypatch.setattr(country_analysis, 'hk_pack_metadata', metadata)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'done', window.log.toPlainText()
    for name in ('Classified_Addresses.csv', 'Country_Diagnostics.csv', 'Country_Summary.csv'):
        assert (direct / name).read_bytes() == (tmp_path / 'export' / name).read_bytes()
    assert ('Hong Kong: test' if enabled else 'Hong Kong: disabled') in window.source_versions.text()
    if enabled:
        assert validation_threads and all(ident != main_thread for ident in validation_threads)
    else:
        assert not validation_threads


def test_hk_controls_large_font_remain_reachable_without_clipping(window, app):
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QStyle, QStyleOptionButton
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    window.setFont(QFont('Segoe UI', 18))
    window.resize(960, 720)
    window.show()
    for _ in range(4):
        app.processEvents()
    window.hk_enabled.setFocus()
    app.processEvents()
    option = QStyleOptionButton()
    option.initFrom(window.hk_enabled)
    text = window.hk_enabled.style().subElementRect(
        QStyle.SubElement.SE_CheckBoxContents, option, window.hk_enabled)
    assert window.hk_enabled.fontMetrics().horizontalAdvance(window.hk_enabled.text()) <= text.width()
    assert window.width() == 960
    window.hk_regional_db.setFocus()
    app.processEvents()
    assert window.settings_scroll.viewport().rect().intersects(
        window.hk_regional_db.geometry().translated(window.hk_regional_db.parentWidget().mapTo(
            window.settings_scroll.viewport(), window.hk_regional_db.parentWidget().rect().topLeft())))


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('stop', ['pause', 'cancel'])
def test_real_partial_runs_and_resume_display_checkpoint_selection(
        window, app, tmp_path, monkeypatch, enabled, stop):
    from tests.unit.test_retrieve import geo
    from tests.unit.test_hk_als_builder import build
    from world_address_engine.jobs import country_analysis
    configure(window, tmp_path)
    source = tmp_path / 'synthetic.csv'
    source.write_text('NAME_ADDRESS_LINE1\nJapan\nChina\nHong Kong\n', encoding='utf-8')
    global_db = geo(tmp_path)
    root = tmp_path / 'hk'
    root.mkdir()
    build(root)
    window.geo_db.setText(str(global_db))
    window.hk_regional_db.setText(str(root / 'pack' / 'pack.db'))
    window.hk_enabled.setChecked(enabled)
    original_analyze = country_analysis.analyze_job
    original_resume = country_analysis.resume_analysis
    main_ident = threading.get_ident()
    checkpoint_reads = []
    original_read = Path.read_text
    checkpoint = tmp_path / 'export' / '.country-state' / 'config.json'

    def read_text(path, *args, **kwargs):
        if path == checkpoint:
            checkpoint_reads.append(threading.get_ident())
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read_text)

    def stop_after_commit(function, *args, **kwargs):
        assert threading.get_ident() != main_ident
        kwargs['batch_size' if function is original_analyze else 'max_batches'] = 1
        if stop == 'pause':
            kwargs['max_batches'] = 1
        else:
            cancelled = threading.Event()
            emit = kwargs['on_progress']
            requested = kwargs['cancel_requested']

            def committed(count):
                emit(count)
                cancelled.set()

            kwargs['on_progress'] = committed
            kwargs['cancel_requested'] = lambda: cancelled.is_set() or requested()
            kwargs.pop('max_batches', None)
        result = function(*args, **kwargs)
        return result

    def analyze(*args, **kwargs):
        return stop_after_commit(original_analyze, *args, **kwargs)

    def resume(*args, **kwargs):
        return stop_after_commit(original_resume, *args, **kwargs)

    monkeypatch.setattr(country_analysis, 'analyze_job', analyze)
    monkeypatch.setattr(country_analysis, 'resume_analysis', resume)
    expected = 'Hong Kong: test' if enabled else 'Hong Kong: disabled'
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == ('paused' if stop == 'pause' else 'cancelled')
    assert expected in window.source_versions.text()
    assert checkpoint_reads and all(ident != main_ident for ident in checkpoint_reads)
    # This is the real checkpoint written by the runner, not fabricated metadata.
    saved = json.loads(original_read(checkpoint, encoding='utf-8'))
    assert window._last_report['run_metadata']['hk_regional'] == saved['hk_regional']
    window.hk_enabled.setChecked(not enabled)
    window.hk_regional_db.setText('different-current-choice.db')
    window.resume_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == ('paused' if stop == 'pause' else 'cancelled')
    assert expected in window.source_versions.text()
    assert window._last_report['committed_records'] == 2
    monkeypatch.setattr(country_analysis, 'resume_analysis', original_resume)
    window.resume_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'done', window.log.toPlainText()
    assert expected in window.source_versions.text()
    assert all(ident != main_ident for ident in checkpoint_reads)


@pytest.mark.parametrize('saved', [None, 'not JSON', '[]', '{"job_kind":"other"}',
                                 '{"job_kind":"country-analysis"}'])
def test_missing_partial_metadata_is_unavailable_not_disabled(window, app, tmp_path, monkeypatch, saved):
    configure(window, tmp_path)

    def analyze(*args, **kwargs):
        if saved is not None:
            checkpoint = tmp_path / 'export' / '.country-state'
            checkpoint.mkdir(parents=True)
            (checkpoint / 'config.json').write_text(saved, encoding='utf-8')
        return {'job_kind': 'country-analysis', 'run_status': 'PAUSED', 'committed_records': 0}

    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'paused'
    assert 'Hong Kong: unavailable' in window.source_versions.text()
