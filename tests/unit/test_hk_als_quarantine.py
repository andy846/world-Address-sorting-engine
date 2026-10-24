"""Partial source coverage is explicit, traceable and never repairs invalid rows."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from tests.unit.test_hk_als_builder import feature, inputs
from world_address_engine.data.hk_als_builder import build_als_pack


def source(tmp_path):
    bad = feature('99')
    del bad['geometry']['coordinates']
    foreign = feature('88')
    foreign['properties']['Address']['PremisesAddress']['EngPremisesAddress']['Region'] = 'JP'
    return inputs(tmp_path, [feature('12'), bad, feature('12'), feature('14'), foreign])


def run_build(archive, schema, out, **kwargs):
    return build_als_pack(archive, schema, out, source_date='2026-10-23',
                          pack_version='test-partial', **kwargs)


def test_partial_mode_keeps_only_valid_records_and_complete_hashed_locators(tmp_path):
    archive, schema = source(tmp_path)
    original = archive.read_bytes(), schema.read_bytes()
    out = tmp_path / 'partial'
    manifest = run_build(archive, schema, out, quarantine_invalid=True)
    receipt = (out / 'quarantine.jsonl').read_bytes()
    rejected = [json.loads(line) for line in receipt.splitlines()]
    assert rejected == [
        {'source_member': 'addresses.geojson', 'source_index': 2, 'reason': 'feature_schema'},
        {'source_member': 'addresses.geojson', 'source_index': 5, 'reason': 'feature_schema'},
    ]
    assert manifest['source_validation'] == {
        'policy': 'quarantine-invalid', 'coverage': 'partial', 'feature_count': 5,
        'valid_feature_count': 3, 'quarantined_feature_count': 2,
        'quarantine_file': 'quarantine.jsonl',
        'quarantine_sha256': hashlib.sha256(receipt).hexdigest(),
    }
    audit = json.loads((out / 'audit.json').read_text(encoding='utf8'))
    assert (audit['valid_count'], audit['invalid_count'], audit['duplicate_count']) == (3, 2, 1)
    assert audit['status'] == 'complete' and audit['validation_policy'] == 'quarantine-invalid'
    assert manifest['record_count'] == 2
    with closing(sqlite3.connect(out / 'pack.db')) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('SELECT number_from FROM hk_addresses ORDER BY number_from').fetchall() == [('12',), ('14',)]
    assert original == (archive.read_bytes(), schema.read_bytes())


def test_default_strict_mode_still_blocks_any_invalid_feature(tmp_path):
    archive, schema = source(tmp_path)
    out = tmp_path / 'strict'
    with pytest.raises(ValueError, match='Invalid features'):
        run_build(archive, schema, out)
    assert not (out / 'pack.db').exists()
    assert json.loads((out / 'audit.json').read_text())['validation_policy'] == 'strict'


@pytest.mark.parametrize('quarantine', [False, True])
def test_clean_snapshot_coverage_is_complete_not_geographic_completeness(tmp_path, quarantine):
    archive, schema = inputs(tmp_path)
    out = tmp_path / 'pack'
    manifest = run_build(archive, schema, out, quarantine_invalid=quarantine)
    meta = manifest['source_validation']
    assert meta['coverage'] == 'complete' and meta['quarantined_feature_count'] == 0
    assert meta['feature_count'] == meta['valid_feature_count'] == 1
    if quarantine:
        assert (out / 'quarantine.jsonl').read_bytes() == b''
        assert meta['quarantine_sha256'] == hashlib.sha256(b'').hexdigest()
    else:
        assert meta['quarantine_file'] is None and meta['quarantine_sha256'] is None
        assert not (out / 'quarantine.jsonl').exists()


def test_all_invalid_source_is_not_a_usable_pack(tmp_path):
    bad = feature()
    bad['geometry']['coordinates'] = [0, 0]
    archive, schema = inputs(tmp_path, [bad])
    out = tmp_path / 'pack'
    with pytest.raises(ValueError, match='No valid addresses'):
        run_build(archive, schema, out, quarantine_invalid=True)
    assert not (out / 'pack.db').exists()
    assert not (out / 'manifest.json').exists()


def test_quarantine_does_not_bypass_malformed_member_or_envelope(tmp_path):
    archive, schema = inputs(tmp_path, envelope={'type': 'WrongCollection'})
    # Fixture schema constrains collection type; the entire source must fail.
    spec = json.loads(schema.read_text())
    spec['properties']['type'] = {'const': 'FeatureCollection'}
    schema.write_text(json.dumps(spec), encoding='utf8')
    out = tmp_path / 'pack'
    with pytest.raises(ValueError, match='envelope'):
        run_build(archive, schema, out, quarantine_invalid=True)
    assert not (out / 'pack.db').exists()


def test_cli_requires_explicit_quarantine_flag(tmp_path):
    archive, schema = source(tmp_path)
    command = [sys.executable, str(Path(__file__).resolve().parents[2] / 'tools/build_hk_als_pack.py'),
               str(archive), str(schema), str(tmp_path / 'partial'), '--source-date', '2026-10-23',
               '--pack-version', 'test-partial', '--quarantine-invalid']
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / 'partial/manifest.json').read_text())
    assert manifest['source_validation']['coverage'] == 'partial'
