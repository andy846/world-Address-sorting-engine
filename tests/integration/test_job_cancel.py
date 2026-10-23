"""Cancellation and checkpoint hygiene in the streaming runner.

The independent review of commit 0957f1d found that a cancel was ignored for
any job smaller than one batch (the job published anyway), and that the
plaintext customer shards were left in the output folder after a successful
run.
"""

from pathlib import Path

from tests.unit.test_classify import hkp
from tests.unit.test_retrieve import geo
from world_address_engine.jobs.runner import resume_job, run_job


def source(path: Path, addresses):
    import csv
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2'])
        for address in addresses:
            writer.writerow(['Recipient', address])


def test_a_cancel_before_the_first_batch_publishes_nothing(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, [f'Springfield {n}' for n in range(50)])
    master = hkp(tmp_path)
    out = tmp_path / 'out'
    result = run_job(data, out, geo(tmp_path), master.db_path, {},
                     batch_size=10_000, allow_unverified_reference_data=True,
                     approval_manifest=master.manifest_path,
                     approval_key=master.key_path, cancel=lambda: True)
    assert result['run_status'] == 'CANCELLED'
    assert not (out / 'Run_Manifest.json').exists()


def test_a_cancelled_job_can_be_resumed_without_duplicates(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['Mumbai, India'] * 40)
    master = hkp(tmp_path)
    out = tmp_path / 'out'
    calls = {'n': 0}

    def cancel():
        calls['n'] += 1
        return calls['n'] > 1

    result = run_job(data, out, geo(tmp_path), master.db_path, {},
                     batch_size=10, allow_unverified_reference_data=True,
                     approval_manifest=master.manifest_path,
                     approval_key=master.key_path, cancel=cancel)
    assert result['run_status'] == 'CANCELLED'
    assert not (out / 'Run_Manifest.json').exists()
    counts = resume_job(out)
    assert counts['MATCHED'] == 40
    import csv
    with (out / 'Classified_Addresses.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 40
    assert [row['Source_Record_No'] for row in rows] == [str(n) for n in range(1, 41)]


def test_a_finished_run_removes_the_plaintext_customer_shards(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['Mumbai, India', 'Tokyo, Japan'])
    master = hkp(tmp_path)
    out = tmp_path / 'out'
    run_job(data, out, geo(tmp_path), master.db_path, {},
            batch_size=10, allow_unverified_reference_data=True,
            approval_manifest=master.manifest_path,
            approval_key=master.key_path)
    assert not (out / '.job-state').exists()


def test_the_operator_can_keep_the_checkpoint(tmp_path):
    data = tmp_path / 'sample.csv'
    source(data, ['Mumbai, India', 'Tokyo, Japan'])
    master = hkp(tmp_path)
    out = tmp_path / 'out'
    run_job(data, out, geo(tmp_path), master.db_path, {},
            batch_size=10, allow_unverified_reference_data=True,
            approval_manifest=master.manifest_path,
            approval_key=master.key_path, keep_checkpoint=True)
    assert (out / '.job-state').is_dir()
