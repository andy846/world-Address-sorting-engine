from datetime import datetime
from pathlib import Path
import pytest
from world_address_engine.gui import country_app as gui
from tests.integration.test_country_gui import app, window, reference_settings


def test_run_folder_is_atomic_unique_and_parent_is_not_run_folder(tmp_path):
    allocate = getattr(gui, 'allocate_run_directory', None)
    assert callable(allocate), 'GUI needs atomic fresh run directory allocation'
    source = tmp_path / 'addresses.csv'
    source.touch()
    instant = datetime(2026, 10, 26, 12, 34, 56)
    first = allocate(source, now=instant)
    second = allocate(source, now=instant)
    assert first.name == 'addresses_output_20261026_123456'
    assert second.name == first.name + '_01'
    assert first.is_dir() and second.is_dir()
    custom = tmp_path / 'custom'
    assert allocate(source, custom, now=instant).parent == custom


def test_discovery_works_outside_project_and_prefers_extended(tmp_path, monkeypatch):
    root = tmp_path / 'installation'
    cwd = tmp_path / 'elsewhere'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    for profile in ('compact', 'extended'):
        folder = root / 'packs' / f'geonames-{profile}-global-2026-10-26-k2'
        folder.mkdir(parents=True)
        (folder / 'pack.db').touch()
    discover = getattr(gui, 'discover_pack', None)
    assert callable(discover), 'GUI needs discovery with explicit installation roots'
    assert 'extended' in discover('geo', roots=[root])
    assert discover('hk', roots=[root]) == ''


def test_gui_preflight_precedes_allocation_and_fresh_runs_never_reuse(app, window, tmp_path, monkeypatch):
    from tests.integration.test_country_gui import configure, install_runner, report, wait
    configure(window, tmp_path)
    window.hk_enabled.setChecked(False)
    outputs = []
    def analyze(source, output, *args, **kwargs):
        outputs.append(output)
        assert output.is_dir() and not list(output.iterdir())
        return report()
    install_runner(monkeypatch, analyze)
    window.start_job()
    wait(app, lambda: not window.busy)
    first = window._output_dir
    assert first.parent == tmp_path / 'export'
    assert window.output_dir.text() == str(tmp_path / 'export')
    window.start_job()
    wait(app, lambda: not window.busy)
    assert len(set(outputs)) == 2
    window.address_columns.clear()
    window.address_columns.addItem('Missing')
    window.address_columns.item(0).setSelected(True)
    before = set((tmp_path / 'export').iterdir())
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed'
    assert set((tmp_path / 'export').iterdir()) == before


def test_mapping_failure_leaves_no_output_parent(window, app, tmp_path, monkeypatch):
    from tests.integration.test_country_gui import configure, wait
    from world_address_engine.data import zone_mappings
    configure(window, tmp_path)
    def invalid(*args):
        raise ValueError('Invalid zone catalogue')
    monkeypatch.setattr(zone_mappings, 'load_zone_mappings', invalid)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed'
    assert not (tmp_path / 'export').exists()


def test_manual_pack_override_and_hk_off_survive_reopen(app, reference_settings):
    from tests.integration.test_country_gui import wait
    first = gui.CountryAnalysisWindow()
    first.geo_db.setText('manual-global.db')
    first.hk_regional_db.setText('manual-hk.db')
    first.hk_enabled.setChecked(False)
    first.close()
    wait(app, lambda: not first._lookup_thread.isRunning())
    second = gui.CountryAnalysisWindow()
    try:
        assert second.geo_db.text() == 'manual-global.db'
        assert second.hk_regional_db.text() == 'manual-hk.db'
        assert not second.hk_enabled.isChecked()
    finally:
        second.close()
        wait(app, lambda: not second._lookup_thread.isRunning())


def test_enabled_missing_hk_does_not_allocate(window, app, tmp_path):
    from tests.integration.test_country_gui import configure, wait
    configure(window, tmp_path)
    window.hk_enabled.setChecked(True)
    window.hk_regional_db.clear()
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed'
    assert 'Hong Kong' in window._last_error
    assert not (tmp_path / 'export').exists()


def _global_manifest(path, **overrides):
    import hashlib
    import json
    from world_address_engine.data.pack_registry import REQUIRED
    manifest = dict.fromkeys(REQUIRED, '')
    manifest.update(pack_id='synthetic', pack_version='test', schema_version=1,
                    profile='EXTENDED_GLOBAL', record_count=20, source_sha256='0' * 64,
                    db_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    manifest.update(overrides)
    target = path.with_name('manifest.json')
    target.write_text(json.dumps(manifest), encoding='utf8')
    return target


@pytest.mark.parametrize('manifest_present', [False, True])
@pytest.mark.parametrize('regional_enabled', [False, True])
def test_preflight_returns_verified_reference_identity(tmp_path, manifest_present, regional_enabled):
    import hashlib
    from tests.unit.test_retrieve import geo
    from tests.unit.test_hk_regional_pack import fixture_pack
    from world_address_engine.data.hk_regional import hk_pack_metadata
    from world_address_engine.gui.country_paths import preflight_references
    path = geo(tmp_path)
    manifest = _global_manifest(path) if manifest_present else None
    hk = fixture_pack(tmp_path / 'hk')[0] if regional_enabled else None
    assert preflight_references(path, hk) == {
        'geo_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'geo_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest else None,
        'hk_regional': hk_pack_metadata(hk) if hk else None,
    }


@pytest.mark.parametrize('changed', ['db', 'manifest'])
def test_gui_rejects_reference_replacement_at_allocation(window, app, tmp_path, monkeypatch, changed):
    import sqlite3
    from tests.integration.test_country_gui import configure, wait
    configure(window, tmp_path)
    path = Path(window.geo_db.text())
    _global_manifest(path)
    allocate = gui.allocate_run_directory

    def replacing_allocate(*args, **kwargs):
        output = allocate(*args, **kwargs)
        if changed == 'db':
            with sqlite3.connect(path) as db:
                db.execute("UPDATE geo_places SET name='Changed Tokyo' WHERE place_id=1")
            # Even a coherent replacement must not become the verified selection.
            _global_manifest(path)
        else:
            _global_manifest(path, pack_version='replacement')
        return output

    monkeypatch.setattr(gui, 'allocate_run_directory', replacing_allocate)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed', window.log.toPlainText()
    assert 'changed' in window._last_error.lower() or 'checksum' in window._last_error.lower()
    assert window._output_dir.is_dir()
    assert not list(window._output_dir.iterdir())


@pytest.mark.parametrize('invalid', ['columns', 'profile_mismatch', 'non_global_profile'])
def test_invalid_global_schema_or_profile_never_allocates(window, app, tmp_path, invalid):
    import sqlite3
    from tests.integration.test_country_gui import configure, wait
    configure(window, tmp_path)
    path = Path(window.geo_db.text())
    with sqlite3.connect(path) as db:
        if invalid == 'columns':
            db.execute('ALTER TABLE geo_places RENAME COLUMN population TO missing_population')
        else:
            db.execute("UPDATE pack_metadata SET profile='NOT_GLOBAL'")
    if invalid == 'profile_mismatch':
        _global_manifest(path)
    window.start_job()
    wait(app, lambda: not window.busy)
    assert window.job_state == 'failed', window.log.toPlainText()
    assert not (tmp_path / 'export').exists()


@pytest.mark.parametrize('changed', ['db', 'manifest'])
def test_preflight_rechecks_bytes_consumed_by_verifier(tmp_path, monkeypatch, changed):
    from tests.unit.test_retrieve import geo
    from world_address_engine.data import pack_registry
    from world_address_engine.gui.country_paths import preflight_references
    path = geo(tmp_path)
    manifest = _global_manifest(path)
    verify = pack_registry.verify_pack

    def replacing_verify(*args):
        result = verify(*args)
        target = path if changed == 'db' else manifest
        with target.open('ab') as stream:
            stream.write(b' ')
        return result

    monkeypatch.setattr(pack_registry, 'verify_pack', replacing_verify)
    with pytest.raises(ValueError, match='changed|checksum'):
        preflight_references(path)
