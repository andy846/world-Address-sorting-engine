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

The smoke test checks window startup, approval refusal and input preview
using only local synthetic fixtures and an explicit JSON report file.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

from gui_entry_point import (
    DISTRIBUTION, EXCLUDED_PACK_PATTERNS, excluded_pack_paths, report_errors,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_NAME = 'WorldAddressEngine'
ENTRY_POINT = REPO_ROOT / 'tools' / 'gui_entry_point.py'


def project_version() -> str:
    """Read the release version from its authoritative project metadata."""
    with (REPO_ROOT / 'pyproject.toml').open('rb') as stream:
        return tomllib.load(stream)['project']['version']


def build_environment() -> dict[str, str]:
    """Keep unrelated native toolchains out of Windows DLL collection."""
    environment = dict(os.environ)
    if os.name == 'nt':
        windows = Path(os.environ['SystemRoot'])
        # Inherited imaging-tool PATH entries can shadow Windows' ICU with
        # an incompatible ABI, even though source imports work correctly.
        environment['PATH'] = os.pathsep.join(map(str, (
            Path(sys.executable).parent, Path(sys.base_prefix),
            Path(sys.base_prefix) / 'DLLs', windows / 'System32', windows,
        )))
    return environment


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
        '--copy-metadata', DISTRIBUTION,
        str(ENTRY_POINT),
    ]
    result = subprocess.run(command, cwd=str(REPO_ROOT), env=build_environment())
    if result.returncode != 0:
        raise SystemExit(f'PyInstaller failed with exit code {result.returncode}')
    produced = output / f'{APP_NAME}.exe' if onefile else output / APP_NAME / f'{APP_NAME}.exe'
    if not produced.is_file():
        raise SystemExit(f'expected the executable at {produced}')
    from PyInstaller.archive.readers import CArchiveReader
    try:
        forbidden = excluded_pack_paths(CArchiveReader(str(produced)).toc)
    except Exception as exc:
        raise SystemExit(f'cannot inspect the built archive: {exc}') from exc
    if not onefile:
        forbidden.extend(excluded_pack_paths(
            path.relative_to(produced.parent) for path in produced.parent.rglob('*')))
    if forbidden:
        raise SystemExit('reference data must not be bundled: ' + ', '.join(forbidden))
    return produced


def smoke_test(executable: Path) -> dict:
    """Exercise a bundle from an empty working directory using a report file."""
    executable = executable.resolve()
    environment = dict(os.environ)
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    # A one-file executable unpacks itself; give it a writable place.
    # A timed-out onefile child may briefly keep an extracted DLL open.
    # Cleanup must not replace the primary smoke-test failure on Windows.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        environment['TEMP'] = work
        environment['TMP'] = work
        report_file = Path(work) / 'self-test.json'
        try:
            result = subprocess.run(
                [str(executable), '--self-test', '--report-file', str(report_file)],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=180, env=environment, cwd=work)
        except subprocess.TimeoutExpired as exc:
            raise SystemExit('the packaged application self-test timed out after 180 seconds') from exc
        except OSError as exc:
            raise SystemExit(f'the packaged application self-test could not start: {exc}') from exc
        try:
            report = json.loads(report_file.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise SystemExit(f'the packaged application self-test report is missing or invalid: {exc}') from exc
        errors = report_errors(report, expected_version=project_version(), require_frozen=True)
        if result.returncode != 0 or errors:
            payload = {'returncode': result.returncode, 'assertion_failures': errors,
                       'report': report, 'stderr': (result.stderr or '')[-4000:]}
            raise SystemExit('the packaged application failed its self-test:\n'
                             + json.dumps(payload, indent=2))
    return report


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
    print(f'packaged {APP_NAME} {project_version()}: {executable} '
          f'({executable.stat().st_size} bytes)')
    if args.smoke_test:
        print(smoke_test(executable))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
