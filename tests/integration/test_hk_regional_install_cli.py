"""Installation works offline from extracted files and never replaces a version."""
import json
from pathlib import Path
import subprocess
import sys

from tests.unit.test_hk_regional_pack import fixture_pack


def test_offline_install_command_verifies_and_refuses_overwrite(tmp_path):
    db, metadata = fixture_pack(tmp_path / 'extracted')
    tool = Path(__file__).resolve().parents[2] / 'tools' / 'install_hk_regional_pack.py'
    command = [sys.executable, str(tool), '--source-dir', str(db.parent),
               '--active-root', str(tmp_path / 'packs')]
    first = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stderr
    receipt = json.loads(first.stdout)
    assert receipt['db_sha256'] == metadata['db_sha256']
    installed = Path(receipt['path'])
    assert installed.is_file()
    before = installed.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert second.returncode != 0
    assert 'already installed' in second.stderr
    assert installed.read_bytes() == before
