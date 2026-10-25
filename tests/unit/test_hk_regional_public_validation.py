"""Public QA sidecar: synthetic runtime packs only, never private inputs."""
from collections import Counter
from contextlib import closing
from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tests.unit.test_hk_regional_matching import make_pack, repin
from tests.unit.test_retrieve import geo
from world_address_engine.data.hk_regional import alias_anchor, normalize_hk_key


def api():
    return importlib.import_module('tools.validate_hk_regional_public')


def regional(tmp_path):
    """Five addresses/region, unique buildings, intentionally shared CSU/street."""
    path = make_pack(tmp_path, count=15)
    with closing(sqlite3.connect(path)) as db, db:
        for i, mark in enumerate('甲乙丙丁戊己庚辛壬癸子丑寅卯辰'):
            address_id = f'synthetic-{i:03}'
            region = ('HK', 'KLN', 'NT')[i // 5]
            db.execute('UPDATE hk_addresses SET region_en=?,region_hant=? WHERE address_id=?',
                       (region, {'HK': '香港', 'KLN': '九龍', 'NT': '新界'}[region], address_id))
            for lang, name in [('en', f'Lantern {chr(65 + i)} Building'),
                               ('zh-Hant', mark + '燈籠大廈'),
                               ('zh-Hans', mark + '灯笼大厦')]:
                key = normalize_hk_key(name)
                db.execute("UPDATE hk_aliases SET name=?,search_key=?,anchor=? "
                           "WHERE address_id=? AND kind='building' AND language=?",
                           (name, key, alias_anchor(key), address_id, lang))
    repin(path)
    return path


def test_public_validation_module_exists():
    assert importlib.util.find_spec('tools.validate_hk_regional_public') is not None


def test_source_selection_is_fixed_stratified_and_uses_one_address_id(tmp_path, monkeypatch):
    path = regional(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('selection invoked a predictor')
    monkeypatch.setattr(api(), 'CountryClassifier', forbidden)
    monkeypatch.setattr(api(), 'HKRegionalMatcher', forbidden)
    bank = api().build_casebank(path)
    assert bank == api().build_casebank(path)
    assert bank['pack']['db_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert Counter(entity['region'] for entity in bank['entities']) == {'HK': 4, 'KLN': 4, 'NT': 4}
    assert [entity['address_id'] for entity in bank['entities']] == [
        f'synthetic-{i:03}' for i in (0, 1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13)]
    assert len(bank['cases']) == 336
    assert Counter(case['kind'] for case in bank['cases']) == {
        'positive': 48, 'foreign': 144, 'wrong_house': 48, 'building_only': 48, 'street_only': 48}
    assert all('99999999' in c['text'] for c in bank['cases'] if c['kind'] == 'wrong_house')
    assert len({case['case_id'] for case in bank['cases']}) == 336
    for entity in bank['entities']:
        assert entity['source_member'] == 'fixture.geojson'
        assert entity['csu_id'] == 'SYNTHETIC-CSU'
        assert entity['number'] == '10'
        for kind in ('building', 'street'):
            assert set(entity['aliases'][kind]) == {'en', 'zh-Hant', 'zh-Hans'}
            for lang, alias in entity['aliases'][kind].items():
                assert alias['address_id'] == entity['address_id']
                assert alias['derived'] == int(lang == 'zh-Hans')
    positives = [case for case in bank['cases'] if case['kind'] == 'positive']
    assert len(positives) == 48
    assert Counter(case['form'] for case in positives) == dict.fromkeys(('en', 'hant', 'hans', 'mixed'), 12)
    assert all(case['expected_country'] == 'HK' for case in positives)
    assert all('Hong Kong' not in case['text'] and '\nHK' not in case['text'] for case in positives)
    assert 'same address ID' in bank['limitations']
    assert 'typed building' in bank['limitations']
    assert 'global accuracy' in bank['limitations']


@pytest.mark.parametrize('mutation', ['no_hans', 'derived_english', 'official_hans', 'no_street_hant',
                                     'conflict', 'unsupported_number', 'wrong_region',
                                     'overlap', 'untyped'])
def test_source_ineligible_addresses_cannot_be_rescued_by_prediction(tmp_path, mutation, monkeypatch):
    path = regional(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        if mutation == 'no_hans':
            db.execute("DELETE FROM hk_aliases WHERE language='zh-Hans'")
        elif mutation == 'derived_english':
            db.execute("UPDATE hk_aliases SET derived=1 WHERE language='en'")
        elif mutation == 'official_hans':
            db.execute("UPDATE hk_aliases SET derived=0 WHERE language='zh-Hans'")
        elif mutation == 'no_street_hant':
            db.execute("DELETE FROM hk_aliases WHERE language='zh-Hant' AND kind='street'")
        elif mutation == 'conflict':
            db.execute('UPDATE hk_addresses SET number_conflict=1')
        elif mutation == 'unsupported_number':
            db.execute("UPDATE hk_addresses SET number_from='99999999',number_to='99999999'")
        elif mutation == 'wrong_region':
            db.execute("UPDATE hk_addresses SET region_en=NULL,region_hant=NULL")
        elif mutation == 'overlap':
            db.execute("UPDATE hk_aliases SET search_key='orchid road' WHERE kind='building' AND language='en'")
        else:
            db.execute("UPDATE hk_aliases SET name='Untyped' WHERE kind='building'")
    repin(path)
    def forbidden(*args, **kwargs):
        pytest.fail('selection invoked a predictor')
    monkeypatch.setattr(api(), 'CountryClassifier', forbidden)
    monkeypatch.setattr(api(), 'HKRegionalMatcher', forbidden)
    with pytest.raises(ValueError, match='four|4'):
        api().build_casebank(path)


def test_shared_csu_cannot_join_aliases_from_different_addresses(tmp_path):
    path = regional(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DELETE FROM hk_aliases WHERE address_id IN ('synthetic-000','synthetic-001') "
                   "AND kind='building'")
        db.execute("DELETE FROM hk_aliases WHERE address_id IN ('synthetic-002','synthetic-003','synthetic-004') "
                   "AND kind='street'")
    repin(path)
    with pytest.raises(ValueError, match='four|4'):
        api().build_casebank(path)


def test_region_names_and_hant_fallback_are_source_based(tmp_path):
    path = regional(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE hk_addresses SET region_en='HONG KONG' WHERE region_en='HK'")
        db.execute("UPDATE hk_addresses SET region_en='KOWLOON' WHERE region_en='KLN'")
        db.execute("UPDATE hk_addresses SET region_en=NULL WHERE region_en='NT'")
    repin(path)
    assert Counter(e['region'] for e in api().build_casebank(path)['entities']) == {'HK': 4, 'KLN': 4, 'NT': 4}


def test_region_disagreement_fails_source_eligibility(tmp_path):
    path = regional(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE hk_addresses SET region_hant='新界' WHERE region_en='HK'")
    repin(path)
    with pytest.raises(ValueError, match='four|4'):
        api().build_casebank(path)


@pytest.mark.parametrize('mutation', ['checksum', 'foreign_source'])
def test_invalid_pack_or_non_als_provenance_fails_before_output(tmp_path, mutation):
    path = regional(tmp_path)
    if mutation == 'checksum':
        with path.open('ab') as stream:
            stream.write(b'changed')
    else:
        manifest = path.with_name('manifest.json')
        data = json.loads(manifest.read_text(encoding='utf8'))
        data['source_url'] = 'https://www.als.gov.hk.evil.example/ALS-GeoJSON.zip'
        manifest.write_text(json.dumps(data), encoding='utf8')
    output = tmp_path / 'out'
    with pytest.raises(ValueError):
        api().validate(geo(tmp_path), path, output)
    assert not output.exists()


def test_end_to_end_preserves_raw_boundary_and_reports_every_case(tmp_path, monkeypatch):
    path, global_db = regional(tmp_path), geo(tmp_path)
    output = tmp_path / 'out'
    tool = api()
    real = tool.CountryClassifier
    seen = []
    class Observed(real):
        def classify(self, record):
            bank = json.loads((output / 'casebank.json').read_text(encoding='utf8'))
            assert len(bank['cases']) == 336  # written before the first prediction
            assert record.country_hint is None and record.input_error is None
            assert dict(record.fields) == {'Address': record.address_text}
            assert record.address_text == bank['cases'][record.record_no - 1]['text']
            seen.append(record.address_text)
            return super().classify(record)
    monkeypatch.setattr(tool, 'CountryClassifier', Observed)
    before = path.read_bytes(), global_db.read_bytes()
    report = tool.validate(global_db, path, output)
    assert before == (path.read_bytes(), global_db.read_bytes())
    assert len(seen) == 672
    assert report['passed']
    assert report['aggregate']['cases'] == 336
    assert report['aggregate']['baseline_assigned'] >= 144
    assert report['aggregate']['baseline_assigned_changed'] == 0
    assert report['aggregate']['failures'] == 0
    assert report['aggregate']['by_region']['HK']['cases'] == 112
    assert len(report['results']) == 336
    assert report == json.loads((output / 'report.json').read_text(encoding='utf8'))
    bank = json.loads((output / 'casebank.json').read_text(encoding='utf8'))
    assert report['casebank_sha256'] == hashlib.sha256((output / 'casebank.json').read_bytes()).hexdigest()
    for case, result in zip(bank['cases'], report['results'], strict=True):
        assert result['case_id'] == case['case_id']
        assert 'reason' in result['baseline'] and 'reason' in result['enabled']
        if case['kind'] == 'foreign':
            assert result['baseline']['country_code'] == result['enabled']['country_code'] == case['expected_country']
            assert result['baseline'] == result['enabled']
        elif case['kind'] != 'positive':
            assert result['direct'] is None


def test_failed_predictions_are_all_reported_without_resampling(tmp_path, monkeypatch):
    tool = api()
    path = regional(tmp_path)
    expected = tool.build_casebank(path)
    class Misses:
        def __init__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def match(self, text):
            return None
    monkeypatch.setattr(tool, 'HKRegionalMatcher', Misses)
    output = tmp_path / 'out'
    report = tool.validate(geo(tmp_path), path, output)
    assert not report['passed']
    assert report['aggregate']['cases'] == 336
    assert len(report['results']) == 336
    assert json.loads((output / 'casebank.json').read_text(encoding='utf8')) == expected
    assert sum('direct_positive' in r['failures'] for r in report['results']) == 48


def test_full_result_preservation_detects_reason_or_evidence_changes(tmp_path, monkeypatch):
    tool = api()
    real = tool.CountryClassifier
    class Drifts(real):
        def classify(self, record):
            result = super().classify(record)
            if self._hk_regional_path is not None and result.country_code == 'JP':
                return replace(result, reason='changed reason', evidence=('changed evidence',))
            return result
    monkeypatch.setattr(tool, 'CountryClassifier', Drifts)
    report = tool.validate(geo(tmp_path), regional(tmp_path), tmp_path / 'out')
    assert not report['passed']
    assert report['aggregate']['baseline_assigned_changed'] == 48
    assert sum('baseline_assigned_preservation' in r['failures'] for r in report['results']) == 48


def test_existing_casebank_is_not_overwritten(tmp_path):
    output = tmp_path / 'out'
    output.mkdir()
    (output / 'casebank.json').write_text('existing evidence', encoding='utf8')
    with pytest.raises(FileExistsError):
        api().validate(geo(tmp_path), regional(tmp_path), output)
    assert (output / 'casebank.json').read_text(encoding='utf8') == 'existing evidence'


def test_recipient_shaped_source_alias_is_not_sanitized_or_replaced(tmp_path):
    path = regional(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        name = 'Attn: Lantern A Building'
        key = normalize_hk_key(name)
        db.execute("UPDATE hk_aliases SET name=?,search_key=?,anchor=? WHERE "
                   "address_id='synthetic-000' AND kind='building' AND language='en'",
                   (name, key, alias_anchor(key)))
    repin(path)
    bank = api().build_casebank(path)
    assert bank['entities'][0]['aliases']['building']['en']['name'] == name
    report = api().validate(geo(tmp_path), path, tmp_path / 'out')
    assert not report['passed']
    failed = [r for r in report['results'] if 'direct_positive' in r['failures']]
    assert len(failed) == 2
    assert all('synthetic-000' in r['case_id'] for r in failed)


def test_metadata_change_during_predictions_refuses_completed_report(tmp_path, monkeypatch):
    path = regional(tmp_path)
    real = api().CountryClassifier
    changed = False
    class Changes(real):
        def classify(self, record):
            nonlocal changed
            result = super().classify(record)
            if not changed:
                with path.with_name('manifest.json').open('a', encoding='utf8') as stream:
                    stream.write(' ')
                changed = True
            return result
    monkeypatch.setattr(api(), 'CountryClassifier', Changes)
    output = tmp_path / 'out'
    with pytest.raises(ValueError, match='changed'):
        api().validate(geo(tmp_path), path, output)
    assert (output / 'casebank.json').exists()
    assert not (output / 'report.json').exists()


def test_cli_exit_codes_distinguish_failed_checks_and_invalid_inputs(tmp_path, monkeypatch, capsys):
    args = ['--global-db', 'absent-global.db', '--hk-regional-db', 'absent-hk.db',
            '--output-dir', str(tmp_path / 'out')]
    assert api().main(args) == 2
    assert 'could not complete' in capsys.readouterr().err
    monkeypatch.setattr(api(), 'validate', lambda *args: {'passed': False, 'aggregate': {'failures': 1}})
    assert api().main(args) == 1
    assert json.loads(capsys.readouterr().out)['passed'] is False


def test_cli_runs_offline_without_build_dependencies(tmp_path):
    path, global_db = regional(tmp_path), geo(tmp_path)
    tool_path = Path(__file__).resolve().parents[2] / 'tools' / 'validate_hk_regional_public.py'
    runner = '''
import importlib.abc
import runpy
import sys
class RuntimeOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'ijson', 'jsonschema', 'world_address_engine.data.hk_als_builder'}:
            raise AssertionError('build dependency imported: ' + fullname)
sys.meta_path.insert(0, RuntimeOnly())
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
    result = subprocess.run([sys.executable, '-c', runner, str(tool_path), '--global-db', str(global_db),
                             '--hk-regional-db', str(path), '--output-dir', str(tmp_path / 'cli')],
                            capture_output=True, text=True, encoding='utf8')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['passed']
    source = tool_path.read_text(encoding='utf8')
    assert 'hk_als_builder' not in source and 'ijson' not in source and 'jsonschema' not in source
