"""Only invented source records and publicly sourced institution controls."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
from types import ModuleType, SimpleNamespace

import pytest

from tests.unit.test_retrieve import geo
from world_address_engine.jobs.country_analysis import analyze_job
from tests.unit.test_country_benchmark_verify import schema2_case, read, write, rehash, ZONE_IDENTITY


@pytest.fixture
def synthetic_v2(schema2_case, monkeypatch, tmp_path):
    """A baseline and data API double; no dependency on the pending writer."""
    source, baseline, block = schema2_case
    rows = read(source)
    write(source, [['Address', 'Note'], *[row[:2] for row in rows[1:]]])
    rows = read(baseline / 'Classified_Addresses.csv')
    write(baseline / 'Classified_Addresses.csv', [
        ['Address', 'Note', 'Country_Code', 'Zone_Code', 'NOVSN_Zone_Code'],
        *[row[:2] + row[-3:] for row in rows[1:]]])
    pack = geo(tmp_path)
    module = tool()
    from world_address_engine.data.country_codes import load_country_codes
    from world_address_engine.jobs.country_analysis import _catalogue_metadata
    manifest_path = baseline / 'Run_Manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    manifest['run_metadata'].update(
        rules_version=module.COUNTRY_RULES_VERSION, geo_sha256=module.file_sha256(pack),
        address_columns=['Address'], hk_regional=None,
        **_catalogue_metadata(load_country_codes()))
    manifest_path.write_text(json.dumps(manifest), encoding='utf8')
    rehash(source, baseline)
    zones = SimpleNamespace(entries={'HK': object(), 'JP': object()},
                            version=ZONE_IDENTITY['version'],
                            source_sha256=ZONE_IDENTITY['source_sha256'],
                            fingerprint=ZONE_IDENTITY['sha256'])
    api = ModuleType('world_address_engine.data.zone_mappings')
    api.load_zone_mappings = lambda: zones
    def zone_values(code, catalogue=None):
        if not code:
            return '', ''
        return {'HK': ('LOCAL', 'A'), 'JP': ('Japan', 'F')}[code]
    api.zone_values = zone_values
    monkeypatch.setitem(sys.modules, api.__name__, api)
    controls_path = tmp_path / 'controls.json'
    controls_path.write_text(json.dumps({'schema_version': 1, 'controls': [
        {'control_id': 'public-hk', 'lines': ['Hong Kong'], 'expected_code': 'HK',
         'source_url': 'https://example.org/location'}]}), encoding='utf8')
    return module, source, baseline, pack, controls_path, zones


def test_schema2_prepare_pins_identity_and_independent_zone_pairs(synthetic_v2, tmp_path):
    module, source, baseline, pack, public, _ = synthetic_v2
    work = tmp_path / 'private'
    info = module.prepare_workload(source, baseline, public, work, pack, repeats=1, control_rows=0)
    oracle = json.loads((work / 'oracle.json').read_text(encoding='utf8'))
    assert info['report_schema_version'] == 2
    assert info['generated_columns'] == ['Country_Code', 'Zone_Code', 'NOVSN_Zone_Code']
    assert info['zone_mapping'] == oracle['zone_mapping'] == ZONE_IDENTITY
    assert [(row['zone_code'], row['novsn_zone_code']) for row in oracle['block']] == [
        ('LOCAL', 'A'), ('', '')]


def test_original_zone_named_fields_survive_without_influencing_generated_zones(synthetic_v2, tmp_path):
    module, source, baseline, pack, public, _ = synthetic_v2
    rows = read(source)
    write(source, [rows[0] + ['Zone_Code', 'NOVSN_Zone_Code'],
                   *[row + ['=untrusted', 'original'] for row in rows[1:]]])
    path = baseline / 'Classified_Addresses.csv'
    rows = read(path)
    write(path, [rows[0][:-3] + ['Zone_Code', 'NOVSN_Zone_Code'] + rows[0][-3:],
                 *[row[:-3] + ["'=untrusted", 'original'] + row[-3:] for row in rows[1:]]])
    rehash(source, baseline)
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, public, work, pack, repeats=1, control_rows=0)
    oracle = json.loads((work / 'oracle.json').read_text(encoding='utf8'))
    assert oracle['block'][0]['fields']['Zone_Code'] == '=untrusted'
    assert oracle['block'][0]['zone_code'] == 'LOCAL'
    assert oracle['block'][0]['novsn_zone_code'] == 'A'
    synthetic_run(module, work, baseline, 'full')
    assert module.verify_workload(work, 'full')['verified']


@pytest.mark.parametrize('damage', ['zone', 'unknown_zone', 'identity', 'tail'])
def test_schema2_baseline_corruption_fails_before_workspace(synthetic_v2, tmp_path, damage):
    module, source, baseline, pack, public, _ = synthetic_v2
    if damage in ('zone', 'unknown_zone'):
        path = baseline / 'Classified_Addresses.csv'
        rows = read(path)
        rows[1 if damage == 'zone' else 2][-2] = 'OTHER'
        write(path, rows)
        rehash(source, baseline)
    else:
        path = baseline / 'Run_Manifest.json'
        manifest = json.loads(path.read_text(encoding='utf8'))
        if damage == 'identity':
            manifest['run_metadata']['zone_mapping']['sha256'] = 'c' * 64
        else:
            manifest['generated_columns'] = ['Country_Code']
        path.write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError):
        module.prepare_workload(source, baseline, public, tmp_path / 'private', pack,
                                repeats=1, control_rows=0)
    assert not (tmp_path / 'private').exists()


def synthetic_run(module, work, baseline, name):
    output = work / name
    shutil.copytree(baseline, output)
    rows = read(work / 'dataset.csv')
    detail = read(output / 'Classified_Addresses.csv')
    write(output / 'Classified_Addresses.csv', [rows[0] + detail[0][-3:],
          *[[module._protect(value) for value in row] + found[-3:]
            for row, found in zip(rows[1:], detail[1:])]])
    rehash(work / 'dataset.csv', output)
    return output


@pytest.mark.parametrize('selected', ['full', 'recovery'])
@pytest.mark.parametrize('key', ['rules_version', 'geo_sha256', 'address_columns',
                                'catalogue_fingerprint', 'zone_mapping'])
def test_every_selected_manifest_must_match_pins(synthetic_v2, tmp_path, selected, key):
    module, source, baseline, pack, public, _ = synthetic_v2
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, public, work, pack, repeats=1, control_rows=0)
    for name in ('full', 'recovery'):
        synthetic_run(module, work, baseline, name)
    path = work / selected / 'Run_Manifest.json'
    manifest = json.loads(path.read_text(encoding='utf8'))
    manifest['run_metadata'][key] = {} if key == 'zone_mapping' else 'changed'
    path.write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError):
        module.verify_workload(work, 'full', compare='recovery')


def test_verify_uses_pinned_pairs_but_run_rejects_current_mapping_change(synthetic_v2, tmp_path, monkeypatch):
    module, source, baseline, pack, public, zones = synthetic_v2
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, public, work, pack, repeats=1, control_rows=0)
    synthetic_run(module, work, baseline, 'full')
    zones.fingerprint = 'c' * 64
    def unavailable_lookup(*args):
        raise AssertionError('verification must use the saved oracle pairs')
    monkeypatch.setattr(sys.modules['world_address_engine.data.zone_mappings'],
                        'zone_values', unavailable_lookup)
    assert module.verify_workload(work, 'full')['verified']
    with pytest.raises(ValueError, match='zone'):
        module.run_workload(work, pack, name='new')
    assert not (work / 'new').exists()


def test_all_public_controls_validated_even_when_not_selected(synthetic_v2, tmp_path):
    module, source, baseline, pack, public, _ = synthetic_v2
    data = json.loads(public.read_text(encoding='utf8'))
    data['controls'].append(dict(data['controls'][0], control_id='bad', expected_code='ZZ'))
    public.write_text(json.dumps(data), encoding='utf8')
    with pytest.raises(ValueError, match='control'):
        module.prepare_workload(source, baseline, public, tmp_path / 'private', pack,
                                repeats=1, control_rows=0)
    assert not (tmp_path / 'private').exists()


def test_unselected_control_label_must_agree_with_classification(synthetic_v2, tmp_path):
    module, source, baseline, pack, public, _ = synthetic_v2
    data = json.loads(public.read_text(encoding='utf8'))
    data['controls'][0]['expected_code'] = 'GB'
    public.write_text(json.dumps(data), encoding='utf8')
    with pytest.raises(ValueError, match='control'):
        module.prepare_workload(source, baseline, public, tmp_path / 'private', pack,
                                repeats=1, control_rows=0)
    assert not (tmp_path / 'private').exists()


@pytest.mark.parametrize('damage', ['hash', 'source_hash', 'count', 'schema', 'missing_zone'])
def test_compare_run_is_exhaustively_verified_even_with_identical_csvs(synthetic_v2, tmp_path, damage):
    module, source, baseline, pack, public, _ = synthetic_v2
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, public, work, pack, repeats=1, control_rows=0)
    for name in ('full', 'recovery'):
        synthetic_run(module, work, baseline, name)
    path = work / 'recovery' / 'Run_Manifest.json'
    manifest = json.loads(path.read_text(encoding='utf8'))
    if damage == 'hash':
        manifest['sha256']['Country_Diagnostics.csv'] = '0' * 64
    elif damage == 'source_hash':
        manifest['run_metadata']['input_sha256'] = '0' * 64
    elif damage == 'count':
        manifest['total_records'] = 3
    elif damage == 'schema':
        del manifest['report_schema_version']
    else:
        del manifest['run_metadata']['zone_mapping']
    path.write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError):
        module.verify_workload(work, 'full', compare='recovery')


def test_mapping_pin_cannot_change_only_in_workload(synthetic_v2, tmp_path):
    module, source, baseline, pack, public, _ = synthetic_v2
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, public, work, pack, repeats=1, control_rows=0)
    path = work / 'workload.json'
    info = json.loads(path.read_text(encoding='utf8'))
    info['zone_mapping']['version'] = 'other'
    path.write_text(json.dumps(info), encoding='utf8')
    with pytest.raises(ValueError, match='oracle'):
        module.verify_workload(work)


def test_legacy_workload_remains_read_only_without_reinterpreting_identity(synthetic_v2, tmp_path):
    module, source, baseline, pack, public, _ = synthetic_v2
    work = tmp_path / 'private'
    module.prepare_workload(source, baseline, public, work, pack, repeats=1, control_rows=0)
    output = synthetic_run(module, work, baseline, 'legacy')
    # Encode the actual historical shapes: one generated cell and no zone pins.
    path = output / 'Classified_Addresses.csv'
    write(path, [row[:-2] for row in read(path)])
    path = output / 'Country_Summary.csv'
    write(path, [row[:3] + row[-2:] for row in read(path)])
    path = output / 'Run_Manifest.json'
    manifest = json.loads(path.read_text(encoding='utf8'))
    del manifest['report_schema_version'], manifest['generated_columns']
    del manifest['run_metadata']['zone_mapping']
    path.write_text(json.dumps(manifest), encoding='utf8')
    rehash(work / 'dataset.csv', output)
    for filename in ('oracle.json', 'workload.json'):
        path = work / filename
        saved = json.loads(path.read_text(encoding='utf8'))
        saved['schema_version'] = 1
        for key in ('report_schema_version', 'generated_columns', 'zone_mapping',
                    'catalogue_metadata', 'reference_metadata'):
            del saved[key]
        if filename == 'oracle.json':
            for item in saved['block']:
                del item['zone_code'], item['novsn_zone_code']
        else:
            saved['oracle_sha256'] = module.file_sha256(work / 'oracle.json')
        path.write_text(json.dumps(saved), encoding='utf8')
    before = {path: path.read_bytes() for path in output.iterdir()}
    assert module.verify_workload(work, 'legacy')['verified']
    assert before == {path: path.read_bytes() for path in before}
    with pytest.raises(ValueError, match='legacy'):
        module.run_workload(work, pack, name='new')
    assert not (work / 'new').exists()


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


def test_regional_benchmark_pins_selection_and_refuses_disabled_or_changed_pack(tmp_path):
    from tests.unit.test_hk_regional_pack import fixture_pack
    from world_address_engine.data.hk_regional import hk_pack_metadata
    source, _, pack = seed(tmp_path)
    regional, _ = fixture_pack(tmp_path / 'regional')
    baseline = tmp_path / 'regional-baseline'
    analyze_job(source, baseline, pack, hk_regional_db=regional)
    module = tool()
    work = tmp_path / 'private'
    with pytest.raises(ValueError, match='regional'):
        module.prepare_workload(source, baseline, controls(tmp_path), work, pack,
                                repeats=2, control_rows=1)
    info = module.prepare_workload(source, baseline, controls(tmp_path), work, pack,
                                   repeats=2, control_rows=1, hk_regional_db=regional)
    assert info['hk_regional'] == hk_pack_metadata(regional)
    with pytest.raises(ValueError, match='regional'):
        module.run_workload(work, pack)
    result = module.run_workload(work, pack, hk_regional_db=regional, stop_after=3, batch_size=1)
    assert result['run_status'] == 'CANCELLED'
    assert result['hk_regional'] == info['hk_regional']
    with regional.open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='checksum|regional'):
        module.run_workload(work, pack, hk_regional_db=regional, resume=True)


def test_verification_rejects_wrong_regional_selection_even_if_all_csvs_match(tmp_path):
    from tests.unit.test_hk_regional_pack import fixture_pack
    source, _, pack = seed(tmp_path)
    regional, _ = fixture_pack(tmp_path / 'regional')
    baseline = tmp_path / 'regional-baseline'
    analyze_job(source, baseline, pack, hk_regional_db=regional)
    module = tool()
    work = tmp_path / 'private'
    info = module.prepare_workload(source, baseline, controls(tmp_path), work, pack,
                                   repeats=2, control_rows=1, hk_regional_db=regional)
    for name, selected in [('correct', regional), ('wrong', None)]:
        analyze_job(work / 'dataset.csv', work / name, pack,
                    {'address_columns': info['address_columns']}, hk_regional_db=selected)
    for name in ('Classified_Addresses.csv', 'Country_Diagnostics.csv', 'Country_Summary.csv'):
        assert (work / 'correct' / name).read_bytes() == (work / 'wrong' / name).read_bytes()
    with pytest.raises(ValueError, match='regional'):
        module.verify_workload(work, 'wrong')
    with pytest.raises(ValueError, match='regional'):
        module.verify_workload(work, 'correct', compare='wrong')
    assert module.verify_workload(work, 'correct')['verified']


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
