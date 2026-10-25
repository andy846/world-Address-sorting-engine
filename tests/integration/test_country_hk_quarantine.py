"""Source exclusions are part of job identity, including fresh-process recovery."""
import json

import pytest

from tests.integration.test_country_analysis import source
from tests.unit.test_hk_als_builder import feature, inputs
from tests.unit.test_retrieve import geo
from world_address_engine.data.hk_als_builder import build_als_pack
from world_address_engine.jobs.country_analysis import analyze_job, resume_analysis


def partial(tmp_path):
    bad = feature()
    bad['geometry']['coordinates'] = [0, 0]
    archive, schema = inputs(tmp_path, [feature(), bad])
    directory = tmp_path / 'regional'
    manifest = build_als_pack(archive, schema, directory, source_date='2026-10-23',
                              pack_version='test-partial', quarantine_invalid=True)
    return directory / 'pack.db', manifest['source_validation']


def test_job_and_recovered_manifest_pin_partial_source_coverage(tmp_path):
    hk, validation = partial(tmp_path)
    data, global_db = source(tmp_path / 'input.csv'), geo(tmp_path)
    out = tmp_path / 'job'
    analyze_job(data, out, global_db, hk_regional_db=hk, batch_size=1, max_batches=1)
    cfg = json.loads((out / '.country-state/config.json').read_text(encoding='utf8'))
    assert cfg['hk_regional']['source_validation'] == validation
    done = resume_analysis(out)
    assert done['run_metadata']['hk_regional']['source_validation'] == validation
    assert not (out / '.country-state').exists()


@pytest.mark.parametrize('mutation', ['missing', 'bytes'])
def test_resume_refuses_changed_exclusion_receipt(tmp_path, mutation):
    hk, _ = partial(tmp_path)
    data, global_db = source(tmp_path / 'input.csv'), geo(tmp_path)
    out = tmp_path / 'job'
    analyze_job(data, out, global_db, hk_regional_db=hk, batch_size=1, max_batches=1)
    receipt = hk.with_name('quarantine.jsonl')
    if mutation == 'missing':
        receipt.unlink()
    else:
        with receipt.open('ab') as stream:
            stream.write(b'changed\n')
    with pytest.raises(ValueError, match='Hong Kong|regional|changed'):
        resume_analysis(out)
    assert not (out / 'Run_Manifest.json').exists()
