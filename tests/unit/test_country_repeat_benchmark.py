"""Only invented source records and publicly sourced institution controls."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.unit.test_retrieve import geo
from world_address_engine.jobs.country_analysis import analyze_job


def tool():
    path = Path(__file__).resolve().parents[2] / 'tools' / 'benchmark_country_repeat.py'
    assert path.is_file(), 'repeat benchmark preparation is not implemented'
    spec = importlib.util.spec_from_file_location('country_repeat_benchmark', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed(tmp_path, extra=()):
    source = tmp_path / 'original.csv'
    with source.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Control no', 'NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2', *extra, '', ''])
        writer.writerow(['0001', 'Example Person', 'Hong Kong', *['x' for _ in extra], '=2+2', 'same'])
        writer.writerow(['0001', 'Example Person', 'Hong Kong', *['x' for _ in extra], '=2+2', 'same'])
        writer.writerow(['0002', 'Other Person', '', *['x' for _ in extra], '', ''])
    pack = geo(tmp_path)
    baseline = tmp_path / 'baseline'
    analyze_job(source, baseline, pack)
    return source, baseline, pack


def controls(tmp_path):
    path = tmp_path / 'controls.json'
    path.write_text(json.dumps({'schema_version': 1, 'verified_date': '2026-10-24', 'controls': [
        {'control_id': 'public-demo', 'lines': ['Example Public Institution', 'Japan'],
         'expected_code': 'JP', 'source_url': 'https://example.org/location'}]}), encoding='utf8')
    return path


def test_preparation_repeats_complete_blocks_and_preserves_original_fields(tmp_path):
    source, baseline, pack = seed(tmp_path)
    before = source.read_bytes()
    work = tmp_path / 'private'
    result = tool().prepare_workload(source, baseline, controls(tmp_path), work, pack,
                                     repeats=3, control_rows=2)
    assert result['total_records'] == 15
    assert result['block_records'] == 5
    assert result['original_records'] == 3
    assert result['control_rows_per_block'] == 2
    assert result['distinct_classification_keys'] == 3
    with (work / 'dataset.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert [r['_Benchmark_Cycle'] for r in rows] == ['1'] * 5 + ['2'] * 5 + ['3'] * 5
    assert [r['_Benchmark_Base_Row'] for r in rows] == ['1', '2', '3', '4', '5'] * 3
    assert [r['Control no'] for r in rows[:3]] == ['0001', '0001', '0002']
    assert rows[0]['Unnamed_1'] == '=2+2'
    assert rows[0]['NAME_ADDRESS_LINE1'] == rows[5]['NAME_ADDRESS_LINE1']
    assert source.read_bytes() == before
    assert (baseline / 'Run_Manifest.json').is_file()
    assert 'Country_Code' not in rows[0] and 'Expected_Code' not in rows[0]
    assert (work / '.gitignore').is_file()
    oracle = json.loads((work / 'oracle.json').read_text(encoding='utf8'))
    assert [x['code'] for x in oracle['block']] == ['HK', 'HK', None, 'JP', 'JP']


@pytest.mark.parametrize('collision', ['_Benchmark_Cycle', '_Benchmark_Base_Row', 'Country_Code', 'Country'])
def test_reserved_hint_or_metadata_columns_are_refused_before_writing(tmp_path, collision):
    # A trusted country input is valid for the app, but invalid for this benchmark.
    source, baseline, pack = seed(tmp_path, extra=(collision,))
    work = tmp_path / 'private'
    with pytest.raises(ValueError, match='column'):
        tool().prepare_workload(source, baseline, controls(tmp_path), work, pack, repeats=2, control_rows=2)
    assert not work.exists()


@pytest.mark.parametrize('bad_repeats,bad_controls', [(0, 2), (True, 2), (2, -1), (2, True)])
def test_invalid_counts_fail_before_writing(tmp_path, bad_repeats, bad_controls):
    source, baseline, pack = seed(tmp_path)
    work = tmp_path / 'private'
    with pytest.raises(ValueError):
        tool().prepare_workload(source, baseline, controls(tmp_path), work, pack,
                                 repeats=bad_repeats, control_rows=bad_controls)
    assert not work.exists()


def test_existing_workspace_and_changed_baseline_are_not_overwritten(tmp_path):
    source, baseline, pack = seed(tmp_path)
    work = tmp_path / 'private'
    work.mkdir()
    (work / 'operator.txt').write_text('keep', encoding='utf8')
    with pytest.raises(FileExistsError):
        tool().prepare_workload(source, baseline, controls(tmp_path), work, pack, repeats=2, control_rows=1)
    assert (work / 'operator.txt').read_text() == 'keep'
    with source.open('a', encoding='utf8') as stream:
        stream.write('changed')
    with pytest.raises(ValueError, match='source|hash'):
        tool().prepare_workload(source, baseline, controls(tmp_path), tmp_path / 'new', pack,
                                 repeats=2, control_rows=1)
    assert not (tmp_path / 'new').exists()


def test_incorrect_public_control_label_is_not_replaced_by_prediction(tmp_path):
    source, baseline, pack = seed(tmp_path)
    path = controls(tmp_path)
    data = json.loads(path.read_text())
    data['controls'][0]['expected_code'] = 'GB'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='control'):
        tool().prepare_workload(source, baseline, path, tmp_path / 'private', pack, repeats=2, control_rows=1)
    assert not (tmp_path / 'private').exists()


def test_explicit_baseline_column_order_is_preserved(tmp_path):
    source, _baseline, pack = seed(tmp_path)
    baseline = tmp_path / 'reversed-baseline'
    order = ['NAME_ADDRESS_LINE2', 'NAME_ADDRESS_LINE1']
    analyze_job(source, baseline, pack, {'address_columns': order})
    work = tmp_path / 'private'
    tool().prepare_workload(source, baseline, controls(tmp_path), work, pack, repeats=2, control_rows=1)
    oracle = json.loads((work / 'oracle.json').read_text(encoding='utf8'))
    assert oracle['address_columns'] == order
    assert oracle['block'][-1]['fields']['NAME_ADDRESS_LINE1'] == 'Japan'


def test_saved_oracle_mutation_is_rejected_before_running_or_verifying(tmp_path):
    source, baseline, pack = seed(tmp_path)
    module = tool()
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, controls(tmp_path), work, pack, repeats=2, control_rows=1)
    path = work / 'oracle.json'
    path.write_text(path.read_text() + ' ', encoding='utf8')
    with pytest.raises(ValueError, match='oracle'):
        module.run_workload(work, pack)
    with pytest.raises(ValueError, match='oracle'):
        module.verify_workload(work)
    assert not (work / 'uninterrupted').exists()


def test_workspace_cannot_accidentally_add_private_files_to_git(tmp_path):
    source, baseline, pack = seed(tmp_path)
    repository = tmp_path / 'repository'
    repository.mkdir()
    subprocess.run(['git', 'init', '-q', str(repository)], check=True, capture_output=True)
    work = repository / 'private'
    tool().prepare_workload(source, baseline, controls(tmp_path), work, pack, repeats=2, control_rows=1)
    for name in ('dataset.csv', 'oracle.json', 'progress-run.json'):
        result = subprocess.run(['git', 'check-ignore', '--quiet', str(work / name)], cwd=repository,
                                capture_output=True)
        assert result.returncode == 0


def test_revision_detects_dirty_to_different_dirty_and_untracked_runtime_changes(tmp_path, monkeypatch):
    module = tool()
    root = tmp_path / 'code'
    (root / 'src').mkdir(parents=True)
    (root / 'tools').mkdir()
    runtime = root / 'src' / 'runtime.py'
    runtime.write_text('value = 1\n', encoding='utf8')
    def git(*args):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
    git('init', '-q')
    git('add', 'src/runtime.py')
    git('-c', 'user.name=Benchmark test', '-c', 'user.email=benchmark@example.invalid',
        'commit', '-qm', 'synthetic baseline')
    monkeypatch.setattr(module, 'ROOT', root)
    runtime.write_text('value = 2\n', encoding='utf8')
    before = module._revision()
    runtime.write_text('value = 3\n', encoding='utf8')
    after = module._revision()
    assert before != after
    assert before['tracked_tree_dirty'] and after['tracked_tree_dirty']
    extra = root / 'tools' / 'country_benchmark_verify.py'
    extra.write_text('value = 4\n', encoding='utf8')
    untracked = module._revision()
    assert untracked != after
    extra.write_text('value = 5\n', encoding='utf8')
    assert module._revision() != untracked


def test_real_cli_fresh_process_cancel_resume_and_exact_reports(tmp_path):
    source, baseline, pack = seed(tmp_path)
    module = tool()
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, controls(tmp_path), work, pack, repeats=3, control_rows=2)
    script = Path(module.__file__)
    environment = dict(os.environ)
    def invoke(operation, *extra):
        command = [sys.executable, str(script), operation, '--workspace', str(work), *extra]
        result = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=45)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    full = invoke('run', '--pack', str(pack), '--name', 'full', '--batch-size', '2')
    assert full['run_status'] == 'COMPLETE' and full['record_count'] == 15
    assert full['classify_calls'] == 30
    assert full['inference_calls'] == 3
    stopped = invoke('run', '--pack', str(pack), '--name', 'recovery', '--batch-size', '2', '--stop-after', '4')
    assert stopped['run_status'] == 'CANCELLED' and stopped['record_count'] == 4
    resumed = invoke('resume', '--pack', str(pack), '--name', 'recovery')
    assert resumed['run_status'] == 'COMPLETE' and resumed['checkpoint_removed']
    verified = invoke('verify', '--name', 'recovery', '--compare', 'full')
    assert verified['verified'] and verified['total_records'] == 15
    assert verified['byte_identical_to_uninterrupted']
