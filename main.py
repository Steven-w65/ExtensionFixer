# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Run Extension Fixer."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from extension_fixer import __version__
from extension_fixer.main_window import MainWindow


def application_directory() -> Path:
    """Use the source folder, or the executable folder in a frozen build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    data_dir = application_directory()
    application = QApplication(sys.argv)
    application.setApplicationName("Extension Fixer")
    application.setOrganizationName("Extension Fixer")
    application.setApplicationVersion(__version__)
    window = MainWindow(data_dir)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
