"""Optional regional selection is pinned separately from global reference data."""
import json

import pytest

from tests.integration.test_country_analysis import source, read
from tests.unit.test_retrieve import geo
from tests.unit.test_hk_regional_pack import fixture_pack
from world_address_engine.jobs.country_analysis import analyze_job, resume_analysis


def test_optional_pack_is_recorded_and_none_preserves_existing_outputs(tmp_path):
    data = source(tmp_path / 'input.csv', ('Japan', '', 'Hong Kong'))
    global_pack = geo(tmp_path)
    hk, _ = fixture_pack(tmp_path / 'hk')
    plain, enabled = tmp_path / 'plain', tmp_path / 'enabled'
    a = analyze_job(data, plain, global_pack)
    b = analyze_job(data, enabled, global_pack, hk_regional_db=hk)
    assert a['run_metadata']['hk_regional'] is None
    pinned = b['run_metadata']['hk_regional']
    assert pinned['path'] == str(hk.resolve())
    assert pinned['version'] == '2026-10-23-r1'
    assert pinned['db_sha256'] and pinned['manifest_sha256']
    for file in ('Classified_Addresses.csv','Country_Diagnostics.csv','Country_Summary.csv'):
        assert (plain/file).read_bytes() == (enabled/file).read_bytes()


@pytest.mark.parametrize('change', ['db', 'manifest', 'missing'])
def test_resume_rejects_a_changed_or_missing_pinned_regional_pack(tmp_path, change):
    data = source(tmp_path / 'input.csv', ('Japan', 'Hong Kong', 'China'))
    global_pack = geo(tmp_path)
    hk, _ = fixture_pack(tmp_path / 'hk')
    out = tmp_path / 'out'
    paused = analyze_job(data, out, global_pack, hk_regional_db=hk, batch_size=1, max_batches=1)
    assert paused['run_status'] == 'PAUSED'
    cfg = json.loads((out/'.country-state/config.json').read_text(encoding='utf8'))
    assert cfg['hk_regional']['path'] == str(hk.resolve())
    if change == 'db':
        with hk.open('ab') as stream:stream.write(b'changed')
    elif change == 'manifest':
        path = hk.with_name('manifest.json')
        meta = json.loads(path.read_text());meta['pack_version']='other'
        path.write_text(json.dumps(meta), encoding='utf8')
    else:
        hk.unlink()
    with pytest.raises(ValueError, match='Hong Kong|regional|changed'):
        resume_analysis(out)
    assert not (out/'Run_Manifest.json').exists()


def test_resume_of_disabled_job_does_not_enable_newly_installed_pack(tmp_path):
    data = source(tmp_path/'input.csv', ('Japan', '', 'Hong Kong'))
    global_pack = geo(tmp_path)
    out = tmp_path/'out'
    analyze_job(data,out,global_pack,batch_size=1,max_batches=1)
    fixture_pack(tmp_path/'hk')
    result = resume_analysis(out)
    assert result['run_metadata']['hk_regional'] is None
    assert result['status_counts']['UNRESOLVED'] == 1


def test_invalid_selected_regional_profile_fails_before_creating_output(tmp_path):
    data = source(tmp_path/'input.csv')
    global_pack = geo(tmp_path)
    out = tmp_path/'out'
    with pytest.raises(ValueError, match='Hong Kong|regional'):
        analyze_job(data,out,global_pack,hk_regional_db=global_pack)
    assert not out.exists()
    hk,_ = fixture_pack(tmp_path/'hk')
    with pytest.raises(ValueError, match='GeoNames|regional|global'):
        analyze_job(data,out,hk)
    assert not out.exists()


def test_regional_database_cannot_masquerade_as_global_with_changed_manifest(tmp_path):
    from world_address_engine.data.geonames_builder import PACK_FORMAT_VERSION
    data = source(tmp_path / 'input.csv', ('Japan',))
    hk, metadata = fixture_pack(tmp_path / 'hk')
    metadata.update(profile='EXTENDED_GLOBAL', pack_format_version=PACK_FORMAT_VERSION)
    hk.with_name('manifest.json').write_text(json.dumps(metadata), encoding='utf8')
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='GeoNames|regional|global'):
        analyze_job(data, out, hk)
    assert not out.exists()


def test_regional_selection_is_rechecked_before_final_report_publication(tmp_path):
    data = source(tmp_path/'input.csv', ('Japan','Hong Kong'))
    global_pack = geo(tmp_path)
    hk,_ = fixture_pack(tmp_path/'hk')
    out = tmp_path/'out'
    def changed(count):
        if count==2:
            path=hk.with_name('manifest.json')
            path.write_text(path.read_text()+' ',encoding='utf8')
    with pytest.raises(ValueError, match='regional|Hong Kong|changed'):
        analyze_job(data,out,global_pack,hk_regional_db=hk,batch_size=1,on_progress=changed)
    assert not (out/'Run_Manifest.json').exists()
