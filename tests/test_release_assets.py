# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from extension_fixer import __version__
from extension_fixer.core import ApplicationSettings, MagicNumberDetector
from main import application_directory


class ReleaseAssetTestCase(unittest.TestCase):
    """Validate files that must accompany a portable source release."""

    @classmethod
    def setUpClass(cls):
        cls.release_root = Path(__file__).resolve().parents[1]

    def test_required_release_assets_and_settings_schema(self):
        for name in (
            "main.py",
            "app.ico",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "requirements.txt",
            "requirements-build.txt",
            "settings.json",
            "custom_magic_formats.json",
            "README.md",
        ):
            self.assertTrue((self.release_root / name).is_file(), name)

        settings = json.loads(
            (self.release_root / "settings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(ApplicationSettings.DEFAULTS), set(settings))
        loaded = ApplicationSettings(
            self.release_root / "settings.json"
        ).load()
        self.assertEqual(set(ApplicationSettings.DEFAULTS), set(loaded))
        self.assertIn(loaded["duplicate_strategy"], (1, 2, 3))
        self.assertEqual("2.0.0", __version__)
        self.assertEqual(self.release_root, application_directory())
        frozen_executable = self.release_root / "dist" / "ExtensionFixer.exe"
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(frozen_executable)),
        ):
            self.assertEqual(frozen_executable.parent, application_directory())

        self.assertTrue(
            (self.release_root / "LICENSE").read_text(encoding="utf-8")
            .startswith("                    GNU GENERAL PUBLIC LICENSE")
        )
        self.assertTrue(
            (self.release_root / "legacy" / "LICENSE")
            .read_text(encoding="utf-8")
            .startswith("MIT License")
        )
        requirements = set(
            (self.release_root / "requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual({
            "PyQt6==6.11.0",
            "PyQt6-Qt6==6.11.2",
            "PyQt6-sip==13.12.0",
        }, requirements)
        build_requirements = (
            self.release_root / "requirements-build.txt"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(["PyInstaller==6.22.2"], build_requirements)

        test_workflow = (
            self.release_root / ".github" / "workflows" / "build.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("pyinstaller", test_workflow.lower())
        self.assertNotIn("upload-artifact", test_workflow.lower())

        windows_workflow = (
            self.release_root
            / ".github"
            / "workflows"
            / "build-windows.yml"
        ).read_text(encoding="utf-8")
        normalized_workflow = windows_workflow.lower()
        self.assertIn("workflow_dispatch:", normalized_workflow)
        self.assertNotIn("pull_request:", normalized_workflow)
        self.assertNotIn("push:", normalized_workflow)
        self.assertIn("pyinstaller", normalized_workflow)
        self.assertIn("--onedir", normalized_workflow)
        self.assertIn("--icon $icon", normalized_workflow)
        self.assertNotIn("--onefile", normalized_workflow)
        self.assertIn("actions/upload-artifact@v7", normalized_workflow)
        self.assertIn("source_commit.txt", normalized_workflow)
        self.assertIn("python-3.12.txt", normalized_workflow)
        self.assertIn("pyinstaller-copying.txt", normalized_workflow)

    def test_every_configured_signature_is_detectable(self):
        detector = MagicNumberDetector(
            self.release_root / "custom_magic_formats.json"
        )
        rules, errors = detector.load()
        self.assertEqual([], errors)
        self.assertGreaterEqual(len(rules), 14)

        with tempfile.TemporaryDirectory() as temporary:
            sample = Path(temporary) / "sample.unknown"
            for expected_extension, parts in rules:
                header = bytearray(MagicNumberDetector.HEADER_SIZE)
                for offset, signature in parts:
                    header[offset:offset + len(signature)] = signature
                sample.write_bytes(header)
                detected, error = detector.detect(sample)
                self.assertEqual("", error)
                self.assertEqual(expected_extension, detected)


if __name__ == "__main__":
    unittest.main()
