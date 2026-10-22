import csv
import json
import os
from pathlib import Path
import subprocess
import sys

from tests.unit.test_classify import hkp
from tests.unit.test_retrieve import geo


def _call(*args):
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2] / 'src')}
    return subprocess.run([sys.executable, '-m', 'world_address_engine.cli', *map(str, args)],
                          text=True, capture_output=True, env=env)


def test_cli_classify_requires_explicit_test_only_for_fixtures(tmp_path):
    source = tmp_path / 'addresses.csv'
    source.write_text('Address,Control no\nIndia,0007\n', encoding='utf8')
    args = ('classify', '--input', source, '--output', tmp_path / 'out',
            '--geo-db', geo(tmp_path), '--hkp-db', hkp(tmp_path), '--address-column', 'Address')
    denied = _call(*args)
    assert denied.returncode != 0
    assert 'not production approved' in denied.stderr
    allowed = _call(*args, '--test-only')
    assert allowed.returncode == 0, allowed.stderr
    result = json.loads(allowed.stdout)
    assert result['MATCHED'] == 1
    manifest = json.loads((tmp_path / 'out' / 'Run_Manifest.json').read_text(encoding='utf8'))
    assert manifest['run_metadata']['data_approval'] == 'TEST_ONLY_UNVERIFIED'


def test_cli_resume_from_paused_job(tmp_path):
    source = tmp_path / 'addresses.csv'
    source.write_text('Address,Control no\nIndia,001\nJapan,002\nMacau,003\n', encoding='utf8')
    first = _call('classify','--input',source,'--output',tmp_path/'out',
                  '--geo-db',geo(tmp_path),'--hkp-db',hkp(tmp_path),
                  '--address-column','Address','--batch-size','2',
                  '--max-batches','1','--test-only')
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)['run_status'] == 'PAUSED'
    assert not (tmp_path / 'out' / 'Run_Manifest.json').exists()
    second = _call('resume','--job-dir',tmp_path/'out')
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)['MATCHED']==3
