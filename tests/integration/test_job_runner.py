import csv
import hashlib
import json
from pathlib import Path

import pytest

from tests.unit.test_classify import hkp
from tests.unit.test_retrieve import geo
from world_address_engine.jobs.runner import run_job, resume_job


def run(data, out, geo_db, master, options=None, **kwargs):
    """Start a job with the signed test master attached."""
    kwargs.setdefault('allow_unverified_reference_data', True)
    return run_job(data, out, geo_db, master.db_path, options or {},
                   approval_manifest=master.manifest_path,
                   approval_key=master.key_path, **kwargs)


def source(path: Path, addresses):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2', 'NAME_ADDRESS_LINE3',
                         'NAME_ADDRESS_LINE4', 'NAME_ADDRESS_LINE5', 'Control no', '', ''])
        for n, address in enumerate(addresses, 1):
            writer.writerow(['Recipient', address, '', '', '', f'{n:06d}', 'extra' if n == 1 else '', ''])


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def test_csv_end_to_end_counts(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['Mumbai, India', 'Tokyo, Japan', 'Macau', 'Springfield'])
    out = tmp_path / 'out'
    result = run(data, out, geo(tmp_path), hkp(tmp_path), {}, batch_size=2)
    assert result['MATCHED'] == 3
    assert result['REVIEW_AMBIGUOUS'] == 1
    details = read(out / 'Classified_Addresses.csv')
    assert [r['Record_ID'] for r in details] == ['000001', '000002', '000003', '000004']
    assert [r['HKP_Destination_Code'] for r in details] == ['IN', 'JP', 'MO', '']
    assert details[0]['Unnamed_1'] == 'extra'
    assert len(read(out / 'Manual_Review.csv')) == 1
    manifest = json.loads((out / 'Run_Manifest.json').read_text(encoding='utf8'))
    assert manifest['total_records'] == 4
    assert manifest['run_metadata']['production_approved'] is False
    assert manifest['run_metadata']['data_approval'] == 'TEST_ONLY_UNVERIFIED'


def test_pause_resume_avoids_duplicate_records(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['India', 'Japan', 'Macau', 'India', 'Japan'])
    out = tmp_path / 'out'
    result = run(data, out, geo(tmp_path), hkp(tmp_path), {}, batch_size=2, max_batches=1)
    assert result['run_status'] == 'PAUSED'
    assert not (out / 'Run_Manifest.json').exists()
    assert len(list((out / '.job-state').glob('*.jsonl'))) == 1
    resumed = resume_job(out)
    assert resumed['MATCHED'] == 5
    details = read(out / 'Classified_Addresses.csv')
    assert [r['Source_Record_No'] for r in details] == ['1', '2', '3', '4', '5']
    assert len(details) == 5
    assert read(out / 'Country_Summary.csv') == [
        {'HKP_Destination_Code':'IN', 'Count':'2'},
        {'HKP_Destination_Code':'JP', 'Count':'2'},
        {'HKP_Destination_Code':'MO', 'Count':'1'},
    ]


def test_mismatched_input_rejects_resume(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['India', 'Japan', 'Macau'])
    out = tmp_path / 'out'
    run(data, out, geo(tmp_path), hkp(tmp_path), {}, batch_size=1, max_batches=1)
    with data.open('a', encoding='utf-8') as f:
        f.write('Changed,Japan,,,,000004,,\n')
    with pytest.raises(ValueError, match='input.*changed|source.*changed'):
        resume_job(out)
    assert not (out / 'Run_Manifest.json').exists()


def test_modified_pack_rejects_resume(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['India', 'Japan', 'Macau'])
    out = tmp_path / 'out'
    geo_db = geo(tmp_path)
    run(data, out, geo_db, hkp(tmp_path), {}, batch_size=1, max_batches=1)
    with geo_db.open('ab') as f:
        f.write(b'unexpected')
    with pytest.raises(ValueError, match='geo.*changed|reference.*changed'):
        resume_job(out)


def test_refuse_unverified_data_by_default(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['India'])
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='approval manifest.*required|not.*approved|unverified'):
        run_job(data, out, geo(tmp_path), hkp(tmp_path).db_path, {})
    assert not (out / 'Run_Manifest.json').exists()


def test_production_run_refuses_a_test_fixture_approval(tmp_path):
    """A TEST_FIXTURE approval can never authorise a production run."""
    data = tmp_path / 'sample.csv'
    source(data, ['India'])
    out = tmp_path / 'out'
    master = hkp(tmp_path)
    with pytest.raises(ValueError, match='test fixture|cannot authorise production'):
        run_job(data, out, geo(tmp_path), master.db_path, {},
                approval_manifest=master.manifest_path, approval_key=master.key_path)
    assert not (out / 'Run_Manifest.json').exists()


def test_forged_catalogue_cannot_pass_the_production_gate(tmp_path):
    """The audit probe: a hand-made SQLite must not reach a production run."""
    import sqlite3
    data = tmp_path / 'sample.csv'
    source(data, ['India'])
    out = tmp_path / 'out'
    forged = tmp_path / 'forged.db'
    with sqlite3.connect(forged) as conn:
        conn.execute("CREATE TABLE metadata (catalogue_version TEXT, csv_sha256 TEXT, "
                     "row_count INTEGER, production_approved INTEGER)")
        conn.execute("INSERT INTO metadata VALUES ('forged', 'x', 1, 1)")
        conn.execute("""CREATE TABLE destinations (destination_id TEXT, code_scheme TEXT,
                         code TEXT, name_en TEXT, name_zh_hant TEXT, name_zh_hans TEXT,
                         source_url TEXT, source_doc_version TEXT, source_section TEXT,
                         source_checksum TEXT, approval_status TEXT, profile TEXT,
                         date_verified TEXT)""")
        conn.execute("""INSERT INTO destinations VALUES ('india','HKP_DESTINATION_2','ZZ',
                         'India','','','https://ec-ship.hongkongpost.hk/x.pdf','v','s',
                         'c','APPROVED','HKP_DESTINATION_2','2026-10-23')""")
    with pytest.raises(ValueError, match='approval manifest.*required|not.*approved|unverified'):
        run_job(data, out, geo(tmp_path), forged, {})
    assert not (out / 'Run_Manifest.json').exists()


def test_corrupted_committed_batch_rejected(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['India', 'Japan'])
    out = tmp_path / 'out'
    run(data, out, geo(tmp_path), hkp(tmp_path), {}, batch_size=1, max_batches=1)
    shard = next((out / '.job-state').glob('*.jsonl'))
    with shard.open('ab') as f:
        f.write(b'tamper')
    with pytest.raises(ValueError, match='checksum|corrupt'):
        resume_job(out)
    assert not (out / 'Run_Manifest.json').exists()


def test_completed_run_rejects_second_run(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['India'])
    out = tmp_path / 'out'
    db = geo(tmp_path); catalogue = hkp(tmp_path)
    run(data, out, db, catalogue, {})
    with pytest.raises(FileExistsError):
        run(data, out, db, catalogue, {})


def test_bad_framing_does_not_publish_completed_manifest(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['India'])
    with data.open('a', encoding='utf-8') as f:
        f.write('"broken,too,few\n')
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='CSV structure'):
        run(data, out, geo(tmp_path), hkp(tmp_path), {}, batch_size=1)
    assert not (out / 'Run_Manifest.json').exists()


def test_source_mutated_during_classification_never_gets_complete_manifest(tmp_path, monkeypatch):
    import world_address_engine.jobs.runner as runner
    data = tmp_path / 'sample.csv'
    source(data, ['India', 'Japan', 'Macau'])
    out = tmp_path / 'out'
    actual = runner.classify_record
    changed = False

    def changes_input_during_batch(record, geo_db, hkp_db, approval=None):
        nonlocal changed
        if record.record_no == 2 and not changed:
            with data.open('a', encoding='utf8') as fp:
                fp.write('Recipient,Japan,,,,000004,,\n')
            changed = True
        return actual(record, geo_db, hkp_db, approval)

    monkeypatch.setattr(runner, 'classify_record', changes_input_during_batch)
    with pytest.raises(ValueError, match='input.*changed'):
        run(data, out, geo(tmp_path), hkp(tmp_path), {}, batch_size=2)
    assert not (out / 'Run_Manifest.json').exists()


def test_invalid_max_batches_refused(tmp_path):
    data = tmp_path / 'sample.csv'; source(data, ['India'])
    with pytest.raises(ValueError, match='max_batches'):
        run(data, tmp_path / 'out', geo(tmp_path), hkp(tmp_path), {}, max_batches=0)
