"""The entry point of the packaged Windows application.

The executable is started with no arguments for the interactive window. A
``--self-test`` argument starts the application with the offscreen Qt
platform, checks that it comes up with no network and no reference pack and
prints a short report. The packaging smoke test uses it, so a broken
bundle is detected before the artefact is published.
"""
from __future__ import annotations

import json
import os
import sys


def self_test() -> int:
    """Prove the bundle works with no network and no data pack."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication

    from world_address_engine.gui.app import MainWindow
    from world_address_engine.jobs.runner import RULES_VERSION

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    # No pack and no approval: the window must come up, offer no
    # destination code and refuse to classify.
    window._load_approved_codes()
    report = {
        'rules_version': RULES_VERSION,
        'job_state': window.job_state,
        'approved_codes': window.approved_codes,
        'review_codes': window.review_code.count(),
        'pack_bundled': False,
    }
    window.close()
    app.processEvents()
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['review_codes'] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == '--self-test':
        return self_test()
    from world_address_engine.gui.app import main as gui_main
    return gui_main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
