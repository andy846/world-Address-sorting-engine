"""Branding resources, installed runtime behavior and Windows build arguments."""

import importlib
from importlib import resources
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def load_branding():
    name = 'world_address_engine.gui.branding'
    assert importlib.util.find_spec(name) is not None, 'branding helper is missing'
    return importlib.import_module(name)


def test_svg_is_a_valid_bundled_vector(app):
    svg = resources.files('world_address_engine.resources').joinpath('wase.svg')
    assert svg.is_file(), 'SVG resource is missing'
    renderer = QSvgRenderer(svg.read_bytes())
    assert renderer.isValid()
    assert renderer.defaultSize().width() == renderer.defaultSize().height()


def test_ico_contains_seven_real_resolution_images():
    ico = resources.files('world_address_engine.resources').joinpath('wase.ico')
    assert ico.is_file(), 'ICO resource is missing'
    data = ico.read_bytes()
    assert struct.unpack_from('<HHH', data) == (0, 1, 7)
    sizes = []
    for index in range(7):
        width, height, palette, reserved, planes, depth, length, offset = (
            struct.unpack_from('<BBBBHHII', data, 6 + index * 16))
        size = width or 256
        assert (height or 256) == size
        assert (palette, reserved, planes, depth) == (0, 0, 1, 32)
        assert offset >= 118
        payload = data[offset:offset + length]
        assert len(payload) == length
        assert payload.startswith(b'\x89PNG\r\n\x1a\n')
        assert struct.unpack_from('>II', payload, 16) == (size, size)
        sizes.append(size)
    assert tuple(sizes) == ICON_SIZES


@pytest.mark.parametrize('frozen', [False, True])
def test_apply_branding_before_show_from_unrelated_cwd(
        app, monkeypatch, tmp_path, frozen):
    branding = load_branding()
    monkeypatch.chdir(tmp_path)
    if frozen:
        monkeypatch.setattr(sys, 'frozen', True, raising=False)
        monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    old_icon = app.windowIcon()
    window = QWidget()
    try:
        branding.apply_branding(window)
        assert not window.isVisible()
        for icon in (window.windowIcon(), app.windowIcon()):
            assert not icon.isNull()
            assert {size.width() for size in icon.availableSizes()} >= set(ICON_SIZES)
            for size in ICON_SIZES:
                pixmap = icon.pixmap(QSize(size, size))
                assert not pixmap.isNull()
                assert pixmap.size() == QSize(size, size)
    finally:
        window.close()
        app.setWindowIcon(old_icon)


@pytest.mark.parametrize('platform', ['linux', 'darwin'])
def test_non_windows_never_accesses_windows_shell(app, monkeypatch, platform):
    branding = load_branding()
    class NoWindowsShell:
        @property
        def shell32(self):
            pytest.fail('Windows shell accessed on another platform')

    monkeypatch.setattr(branding.sys, 'platform', platform)
    monkeypatch.setattr(branding.ctypes, 'windll', NoWindowsShell(), raising=False)
    window = QWidget()
    try:
        branding.apply_branding(window)
        assert not window.windowIcon().isNull()
    finally:
        window.close()


def test_windows_sets_stable_taskbar_identity_before_show(app, monkeypatch):
    branding = load_branding()
    identities = []
    window = QWidget()

    class SetIdentity:
        def __call__(self, identity):
            assert not window.isVisible()
            identities.append(identity)
            return 0

    class Shell:
        SetCurrentProcessExplicitAppUserModelID = SetIdentity()

    class Windows:
        shell32 = Shell()

    monkeypatch.setattr(branding.sys, 'platform', 'win32')
    monkeypatch.setattr(branding.ctypes, 'windll', Windows(), raising=False)
    try:
        branding.apply_branding(window)
        branding.apply_branding(window)
        assert len(identities) == 2
        assert identities[0] == identities[1]
        assert isinstance(identities[0], str) and identities[0].strip()
        assert len(identities[0]) <= 128
        assert ' ' not in identities[0]
        assert not window.windowIcon().isNull()
    finally:
        window.close()


def test_unavailable_windows_shell_does_not_prevent_startup(app, monkeypatch):
    branding = load_branding()
    class UnavailableShell:
        @property
        def shell32(self):
            raise OSError('Windows shell unavailable')

    monkeypatch.setattr(branding.sys, 'platform', 'win32')
    monkeypatch.setattr(branding.ctypes, 'windll', UnavailableShell(), raising=False)
    window = QWidget()
    try:
        branding.apply_branding(window)
        assert not window.windowIcon().isNull()
    finally:
        window.close()


@pytest.mark.parametrize('onefile', [True, False])
def test_pyinstaller_uses_real_ico_and_collects_resources(monkeypatch, tmp_path, onefile):
    writer = pytest.importorskip('PyInstaller.archive.writers').CArchiveWriter
    monkeypatch.syspath_prepend(str(REPO_ROOT / 'tools'))
    packaging = importlib.import_module('package_windows')
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        output = Path(command[command.index('--distpath') + 1])
        root = output if '--onefile' in command else output / packaging.APP_NAME
        root.mkdir(parents=True, exist_ok=True)
        writer(str(root / f'{packaging.APP_NAME}.exe'), [], 'python313.dll')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(packaging.subprocess, 'run', run)
    monkeypatch.chdir(tmp_path)
    assert packaging.build(tmp_path / 'dist', onefile=onefile).is_file()
    command = commands[0]
    assert '--icon' in command, 'Windows executable has no branding icon'
    icon_path = Path(command[command.index('--icon') + 1])
    assert icon_path.is_absolute() and icon_path.is_file()
    assert icon_path.read_bytes() == resources.files(
        'world_address_engine.resources').joinpath('wase.ico').read_bytes()
    assert command[command.index('--collect-all') + 1] == 'world_address_engine.resources'


def test_built_wheel_contains_and_loads_branding(tmp_path):
    # Build a disposable source copy so setuptools never changes the worktree.
    project = tmp_path / 'project'
    project.mkdir()
    shutil.copyfile(REPO_ROOT / 'pyproject.toml', project / 'pyproject.toml')
    shutil.copytree(REPO_ROOT / 'src' / 'world_address_engine',
                    project / 'src' / 'world_address_engine',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    result = subprocess.run(
        [sys.executable, '-c',
         'from setuptools.build_meta import build_wheel; build_wheel("wheelhouse")'],
        cwd=project, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next((project / 'wheelhouse').glob('*.whl'))
    installed = tmp_path / 'installed'
    with zipfile.ZipFile(wheel) as archive:
        for name in ('wase.svg', 'wase.ico'):
            assert f'world_address_engine/resources/{name}' in archive.namelist()
        archive.extractall(installed)
    # Also import directly from the wheel to catch lazy icons whose temporary
    # resource files have disappeared by the time the first window is shown.
    for location in (installed, wheel):
        environment = dict(os.environ, PYTHONPATH=str(location), QT_QPA_PLATFORM='offscreen')
        probe = subprocess.run(
            [sys.executable, '-c',
             'from pathlib import Path; import sys; '
             'from PySide6.QtWidgets import QApplication, QWidget; '
             'from world_address_engine.gui import branding; '
             'assert Path(branding.__file__).is_relative_to(Path(sys.argv[1]).resolve()); '
             'app = QApplication([]); window = QWidget(); '
             'branding.apply_branding(window); '
             'assert not window.windowIcon().isNull(); '
             'assert not app.windowIcon().isNull(); '
             'assert all(not window.windowIcon().pixmap(s, s).isNull() '
             'for s in (16, 24, 32, 48, 64, 128, 256))', str(location)],
            cwd=tmp_path, env=environment, capture_output=True, text=True)
        assert probe.returncode == 0, probe.stdout + probe.stderr
