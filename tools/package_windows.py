"""Package the offline desktop application for Windows.

The executable deliberately does **not** carry a reference database. The
GeoNames packs are 137 MiB (compact) and 1,047 MiB (extended); bundling
them would make the executable unreviewable and would ship data that the
release process has not signed off. The application installs or selects a
pack at run time instead, and the pack carries its own manifest and
checksum.

Usage:

    python tools/package_windows.py --output dist
    python tools/package_windows.py --output dist --smoke-test

The smoke test starts the packaged executable on a machine with no network
and checks that it comes up, refuses to classify without a signed approval
and still answers the preview command.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_NAME = 'WorldAddressEngine'
ENTRY_POINT = REPO_ROOT / 'tools' / 'gui_entry_point.py'

# The packs are installed at run time, never bundled.
EXCLUDED_PACK_PATTERNS = ('geonames-*', '*.sqlite', '*.db')

VERSION = '0.1.0a1'


def build(output: Path, *, onefile: bool = True) -> Path:
    """Run PyInstaller and return the produced executable."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            'PyInstaller is required: python -m pip install "pyinstaller>=6,<7"')
    output.mkdir(parents=True, exist_ok=True)
    work = output / 'build'
    command = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean',
        '--name', APP_NAME,
        '--distpath', str(output),
        '--workpath', str(work),
        '--specpath', str(work),
        '--windowed',
        '--onefile' if onefile else '--onedir',
        # The reference packs are selected at run time and are never added
        # as data files, so they cannot end up inside the executable.
        '--hidden-import', 'world_address_engine.gui.app',
        '--hidden-import', 'world_address_engine.data.geonames_builder',
        str(ENTRY_POINT),
    ]
    result = subprocess.run(command, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        raise SystemExit(f'PyInstaller failed with exit code {result.returncode}')
    produced = output / (f'{APP_NAME}.exe' if onefile else APP_NAME)
    if not produced.exists():
        raise SystemExit(f'expected the executable at {produced}')
    return produced


def smoke_test(executable: Path) -> dict:
    """Start the packaged application with no network and no data pack."""
    import json
    import os
    import tempfile

    environment = dict(os.environ)
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    # A one-file executable unpacks itself; give it a writable place.
    with tempfile.TemporaryDirectory() as work:
        environment['TEMP'] = work
        environment['TMP'] = work
        result = subprocess.run(
            [str(executable), '--self-test'],
            capture_output=True, text=True, timeout=180, env=environment)
    payload = {'returncode': result.returncode,
               'stdout': result.stdout[-4000:],
               'stderr': result.stderr[-4000:]}
    if result.returncode != 0:
        raise SystemExit('the packaged application failed its self test:\n'
                         + json.dumps(payload, indent=2))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPO_ROOT / 'dist')
    parser.add_argument('--onefile', action='store_true', default=True)
    parser.add_argument('--no-onefile', dest='onefile', action='store_false')
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args(argv)

    if os.name != 'nt':
        print('note: this packaging target is Windows; the build may fail here')
    executable = build(args.output, onefile=args.onefile)
    print(f'packaged {executable} '
          f'({executable.stat().st_size} bytes)')
    if args.smoke_test:
        print(smoke_test(executable))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
