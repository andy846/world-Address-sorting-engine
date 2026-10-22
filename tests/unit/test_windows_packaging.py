"""The Windows packaging target must stay honest about what it ships.

The executable is deliberately small: the reference database is installed
at run time and is never bundled, because a multi-gigabyte payload cannot
be reviewed and must not be published without a signed pack manifest.
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'tools'))

from package_windows import APP_NAME, ENTRY_POINT, build, main  # noqa: E402


def test_the_entry_point_exists_and_is_importable():
    assert ENTRY_POINT.is_file()
    source = ENTRY_POINT.read_text(encoding='utf-8')
    assert 'self_test' in source


def test_the_console_and_window_entry_points_are_declared():
    text = (REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'world-address-engine = "world_address_engine.cli:main"' in text
    assert 'world-address-engine-gui = "world_address_engine.gui.app:main"' in text


def test_the_packaging_script_never_bundles_a_reference_database():
    source = (REPO_ROOT / 'tools' / 'package_windows.py').read_text(encoding='utf-8')
    # No pack file is ever handed to PyInstaller as data.
    for forbidden in ("--add-data", "compact_global.sqlite", "extended_global.sqlite",
                      "pack.db"):
        assert forbidden not in source
    assert APP_NAME


def test_the_build_fails_clearly_without_pyinstaller(monkeypatch, tmp_path):
    """A missing PyInstaller has to be a clear message, not a traceback."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'PyInstaller':
            raise ImportError('no pyinstaller here')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    with pytest.raises(SystemExit) as excinfo:
        build(tmp_path)
    assert 'PyInstaller' in str(excinfo.value)


@pytest.mark.skipif(os.name != 'nt', reason='the packaging target is Windows')
def test_the_packaged_executable_passes_its_own_self_test(tmp_path):
    executable = build(tmp_path, onefile=True)
    assert executable.name == f'{APP_NAME}.exe'
    assert executable.stat().st_size > 0
