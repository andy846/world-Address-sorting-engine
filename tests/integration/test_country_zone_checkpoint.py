"""Mapping identity is pinned independently of country-inference evidence."""
import json

import pytest

from tests.integration.test_country_analysis import source, runner
from tests.unit.test_retrieve import geo


def paused(tmp_path):
    job = runner()
    data = source(tmp_path/'input.csv',['Japan']*4)
    output = tmp_path/'output'
    job.analyze_job(data,output,geo(tmp_path),batch_size=1,max_batches=1)
    cfg = output/'.country-state/config.json'
    return job,output,cfg


def test_new_checkpoint_pins_mapping_and_schema(tmp_path):
    _,_,path = paused(tmp_path)
    cfg = json.loads(path.read_text('utf8'))
    assert cfg['schema_version'] == '2026-10-26.country-state.3'
    assert set(cfg['zone_mapping']) == {'version','source_sha256','sha256'}
    assert len(cfg['zone_mapping']['sha256']) == 64


def test_replaced_mapping_pin_cannot_be_resumed(tmp_path):
    job,output,path = paused(tmp_path)
    cfg = json.loads(path.read_text('utf8'))
    cfg['zone_mapping'] = {'version':'different','source_sha256':'0'*64,'sha256':'1'*64}
    path.write_text(json.dumps(cfg),encoding='utf8')
    before = {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='zone mapping'):
        job.resume_analysis(output,max_batches=1)
    assert before == {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}


def test_legacy_checkpoint_is_rejected_without_rewriting_it(tmp_path):
    job,output,path = paused(tmp_path)
    cfg = json.loads(path.read_text('utf8'))
    cfg['schema_version'] = '2026-10-24.country-state.2'
    cfg.pop('zone_mapping',None)
    path.write_text(json.dumps(cfg),encoding='utf8')
    before = {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='v0.2.0'):
        job.resume_analysis(output,max_batches=1)
    assert before == {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}


def test_resumed_export_carries_original_mapping_identity(tmp_path):
    job,output,path = paused(tmp_path)
    cfg = json.loads(path.read_text('utf8'))
    report = job.resume_analysis(output)
    assert report['run_metadata']['zone_mapping'] == cfg['zone_mapping']
    assert report['generated_columns'] == ['Country_Code','Zone_Code','NOVSN_Zone_Code']
