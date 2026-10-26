"""Verified GUI selections stay bound across output allocation and job startup."""
import json
import sqlite3
from contextlib import closing

import pytest

from tests.integration.test_country_analysis import runner, source
from tests.unit.test_retrieve import geo


def setup(tmp_path):
    job=runner()
    data=source(tmp_path/'input.csv')
    pack=geo(tmp_path)
    metadata=job._pack_metadata(pack,job.file_sha256(pack))
    identity={'geo_sha256':job.file_sha256(pack),
              'geo_manifest_sha256':metadata['geo_manifest_sha256'],
              'hk_regional':None}
    return job,data,pack,identity


def test_verified_reference_identity_allows_the_unchanged_run(tmp_path):
    job,data,pack,identity=setup(tmp_path)
    result=job.analyze_job(data,tmp_path/'output',pack,expected_reference_identity=identity)
    assert result['total_records']==4
    assert result['run_metadata']['geo_sha256']==identity['geo_sha256']


@pytest.mark.parametrize('change',['database','manifest','regional','missing_key'])
def test_changed_verified_reference_is_rejected_before_state(tmp_path,change):
    job,data,pack,identity=setup(tmp_path)
    if change=='database':
        with closing(sqlite3.connect(pack)) as db,db:
            db.execute("UPDATE geo_places SET population=population+1 WHERE place_id=1")
    elif change=='manifest':
        pack.with_name('manifest.json').write_text(json.dumps({'profile':'EXTENDED_GLOBAL','pack_version':'changed'}),encoding='utf8')
    elif change=='regional':
        identity['hk_regional']={'path':'previously-selected-pack'}
    else:
        identity.pop('geo_manifest_sha256')
    output=tmp_path/'output'
    with pytest.raises(ValueError,match='reference packs changed after verification'):
        job.analyze_job(data,output,pack,expected_reference_identity=identity)
    assert not output.exists()


def test_declared_database_hash_is_checked_without_gui_pins(tmp_path):
    job,data,pack,identity=setup(tmp_path)
    pack.with_name('manifest.json').write_text(json.dumps({
        'profile':'EXTENDED_GLOBAL','db_sha256':identity['geo_sha256']}),encoding='utf8')
    with closing(sqlite3.connect(pack)) as db,db:
        db.execute("UPDATE geo_places SET population=population+1 WHERE place_id=1")
    output=tmp_path/'output'
    with pytest.raises(ValueError,match='checksum'):
        job.analyze_job(data,output,pack)
    assert not output.exists()
