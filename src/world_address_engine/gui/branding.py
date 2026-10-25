"""Packaged application identity shared by the desktop windows."""

from __future__ import annotations

import ctypes
from importlib import resources
import sys

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget


def apply_branding(window: QWidget) -> None:
    """Set process and window identity; call after QApplication and before show()."""
    if sys.platform == 'win32':
        try:
            set_identity = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
            set_identity.argtypes = [ctypes.c_wchar_p]
            set_identity.restype = ctypes.c_long
            set_identity('WorldAddressEngine.Desktop')
        except (AttributeError, OSError):
            # A minimal Windows shell may omit taskbar identity support.
            pass

    resource = resources.files('world_address_engine.resources').joinpath('wase.ico')
    icon = QIcon()
    with resources.as_file(resource) as path:
        source = QIcon(str(path))
        # Materialize each frame while as_file() is alive, including zip imports.
        for size in (16, 24, 32, 48, 64, 128, 256):
            icon.addPixmap(source.pixmap(QSize(size, size)))
    QApplication.setWindowIcon(icon)
    window.setWindowIcon(icon)
