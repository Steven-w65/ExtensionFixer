# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import csv
import ctypes
import os
import tempfile
import unittest
from pathlib import Path

from extension_fixer.core import (
    ApplicationSettings,
    FileOperations,
    FileScanner,
    MagicNumberDetector,
    export_csv_report,
)


class CoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config_path = self.root / "custom_magic_formats.json"
        self.config_path.write_text(json.dumps({
            "formats": [
                {"extension": "png", "offset": 0, "signature_hex": "89504E470D0A1A0A"},
                {"extension": "webp", "signatures": [
                    {"offset": 0, "signature_hex": "52494646"},
                    {"offset": 8, "signature_hex": "57454250"},
                ]},
            ]
        }), encoding="utf-8")
        self.detector = MagicNumberDetector(self.config_path)
        rules, errors = self.detector.load()
        self.assertEqual(2, len(rules))
        self.assertEqual([], errors)

    def tearDown(self):
        self.temporary.cleanup()

    def test_detection_and_multi_part_signature(self):
        png = self.root / "image.bad"
        png.write_bytes(bytes.fromhex("89504E470D0A1A0A") + b"payload")
        webp = self.root / "photo.bin"
        webp.write_bytes(b"RIFF1234WEBPmore")
        self.assertEqual(("png", ""), self.detector.detect(png))
        self.assertEqual(("webp", ""), self.detector.detect(webp))

    def test_invalid_rule_does_not_replace_active_rules(self):
        self.config_path.write_text(json.dumps({
            "formats": [{"extension": "bad", "offset": 15, "signature_hex": "AABB"}]
        }), encoding="utf-8")
        rules, errors = self.detector.load()
        self.assertTrue(errors)
        self.assertEqual(2, len(rules))

    def test_scanner_status_blacklist_size_and_cancellation(self):
        folder = self.root / "scan"
        folder.mkdir()
        (folder / "repair.wrong").write_bytes(bytes.fromhex("89504E470D0A1A0A"))
        (folder / "normal.png").write_bytes(bytes.fromhex("89504E470D0A1A0A"))
        (folder / "blocked.exe").write_bytes(bytes.fromhex("89504E470D0A1A0A"))
        scanner = FileScanner(self.detector)
        records = list(scanner.scan_iter(
            folder, False, 1024, {".exe"}, lambda _message: None
        ))
        statuses = {record["file_name"]: record["status"] for record in records}
        self.assertEqual("Repair required", statuses["repair.wrong"])
        self.assertEqual("Normal: extension matches", statuses["normal.png"])
        self.assertEqual("Skipped: blacklisted extension", statuses["blocked.exe"])
        self.assertEqual([], list(scanner.scan_iter(
            folder, True, 1024, set(), lambda _message: None, lambda: True
        )))

    def test_settings_validation_and_round_trip(self):
        store = ApplicationSettings(self.root / "settings.json")
        settings = store.load()
        self.assertFalse(settings["automatic_scan_after_repair"])
        self.assertFalse(settings["automatic_scan_after_undo"])
        settings.update({
            "duplicate_strategy": 2,
            "max_size_mb": "64",
            "automatic_scan_after_repair": True,
            "automatic_scan_after_undo": True,
        })
        self.assertEqual((True, ""), store.save(settings))
        loaded = store.load()
        self.assertEqual(2, loaded["duplicate_strategy"])
        self.assertEqual("64", loaded["max_size_mb"])
        self.assertTrue(loaded["automatic_scan_after_repair"])
        self.assertTrue(loaded["automatic_scan_after_undo"])

    def test_csv_report_preserves_metadata_schema(self):
        record = {
            "path": str(self.root / "sample.bad"),
            "relative_path": "sample.bad",
            "file_name": "sample.bad",
            "current_extension": ".bad",
            "detected_extension": ".png",
            "status": "Repair required",
            "size_bytes": 123,
            "size_display": "123 B",
            "planned_path": str(self.root / "sample.png"),
            "error": "",
        }
        report = Path(export_csv_report([record], self.root / "report.csv"))
        with report.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(1, len(rows))
        self.assertEqual(str(self.root / "sample.bad"), rows[0]["full_path"])
        self.assertEqual(".png", rows[0]["detected_real_extension"])
        self.assertEqual("123", rows[0]["size_bytes"])

    def _repair_record(self, path: Path, extension: str = ".png") -> dict:
        return {
            "path": str(path),
            "relative_path": path.name,
            "file_name": path.name,
            "current_extension": path.suffix.lower(),
            "detected_extension": extension,
            "status": "Repair required",
            "size_bytes": path.stat().st_size,
            "size_display": "",
            "planned_path": "",
            "error": "",
        }

    def test_duplicate_strategies(self):
        source = self.root / "sample.bad"
        source.write_bytes(b"source")
        (self.root / "sample.png").write_bytes(b"existing")
        operations = FileOperations(self.root / "operation_log.json")

        planned, conflicts, error = operations.plan_renames(
            [self._repair_record(source)], FileOperations.STRATEGIES[1]
        )
        self.assertFalse(error)
        self.assertTrue(conflicts)
        self.assertEqual("sample_1.png", planned[0][2].name)

        planned, _, error = operations.plan_renames(
            [self._repair_record(source)], FileOperations.STRATEGIES[2]
        )
        self.assertEqual([], planned)
        self.assertFalse(error)

        planned, _, error = operations.plan_renames(
            [self._repair_record(source)], FileOperations.STRATEGIES[3]
        )
        self.assertEqual([], planned)
        self.assertTrue(error)

    def test_backup_repair_and_latest_batch_undo(self):
        source = self.root / "document.bad"
        content = b"original binary content"
        source.write_bytes(content)
        operations = FileOperations(self.root / "operation_log.json")
        result = operations.rename_records(
            [self._repair_record(source)],
            self.root,
            FileOperations.STRATEGIES[1],
            True,
            1024,
            lambda _message: None,
        )
        target = self.root / "document.png"
        self.assertEqual(1, result["renamed"])
        self.assertEqual(content, target.read_bytes())
        backups = list((self.root / "backup").rglob("document.bad"))
        self.assertEqual(1, len(backups))
        self.assertEqual(content, backups[0].read_bytes())

        batch_id, preview, error = operations.preview_latest_batch()
        self.assertFalse(error)
        self.assertEqual("Ready", preview[0]["status"])
        self.assertEqual((1, 0, ""), operations.undo_batch(batch_id, lambda _message: None))
        self.assertEqual(content, source.read_bytes())
        self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == "nt", "Windows short paths are Windows-specific")
    def test_windows_short_path_alias_can_repair_backup_and_undo(self):
        long_root = self.root / "Long Temporary Repair Directory"
        long_root.mkdir()

        buffer_size = 32768
        buffer = ctypes.create_unicode_buffer(buffer_size)
        copied = ctypes.windll.kernel32.GetShortPathNameW(
            str(long_root), buffer, buffer_size
        )
        if not copied or copied >= buffer_size:
            self.skipTest("Windows could not provide an 8.3 short-path alias")
        short_root = Path(buffer.value)
        if os.path.normcase(str(short_root)) == os.path.normcase(str(long_root)):
            self.skipTest("8.3 short-path aliases are disabled on this volume")

        source = short_root / "aliased.bad"
        content = b"alias-safe content"
        source.write_bytes(content)
        operations = FileOperations(self.root / "alias_operation_log.json")
        result = operations.rename_records(
            [self._repair_record(source)],
            long_root,
            FileOperations.STRATEGIES[1],
            True,
            1024,
            lambda _message: None,
        )

        target = long_root / "aliased.png"
        self.assertEqual(1, result["renamed"])
        self.assertEqual(0, result["failed"])
        self.assertEqual(content, target.read_bytes())
        backups = list((long_root / "backup").rglob("aliased.bad"))
        self.assertEqual(1, len(backups))
        self.assertEqual(content, backups[0].read_bytes())

        batch_id, preview, error = operations.preview_latest_batch()
        self.assertEqual("", error)
        self.assertEqual("Ready", preview[0]["status"])
        self.assertEqual((1, 0, ""), operations.undo_batch(batch_id, lambda _: None))
        self.assertEqual(content, (long_root / "aliased.bad").read_bytes())

    def test_corrupt_log_blocks_repair(self):
        source = self.root / "blocked.bad"
        source.write_bytes(b"content")
        log = self.root / "operation_log.json"
        log.write_text("broken", encoding="utf-8")
        operations = FileOperations(log)
        result = operations.rename_records(
            [self._repair_record(source)], self.root, FileOperations.STRATEGIES[1],
            False, 1024, lambda _message: None,
        )
        self.assertEqual(0, result["renamed"])
        self.assertIn("blocked", result["message"].lower())
        self.assertTrue(source.exists())

    def test_repair_rechecks_magic_number_and_current_blacklist(self):
        changed = self.root / "changed.bad"
        changed.write_bytes(bytes.fromhex("89504E470D0A1A0A"))
        changed_record = self._repair_record(changed)
        # Simulate replacement after scan; the expected PNG signature is gone.
        changed.write_bytes(b"not a png")
        operations = FileOperations(self.root / "operation_log.json", self.detector)
        result = operations.rename_records(
            [changed_record], self.root, FileOperations.STRATEGIES[1],
            False, 1024, lambda _message: None,
        )
        self.assertEqual(0, result["renamed"])
        self.assertEqual(1, result["skipped"])
        self.assertTrue(changed.exists())

        blocked = self.root / "blocked.bad"
        blocked.write_bytes(bytes.fromhex("89504E470D0A1A0A"))
        result = operations.rename_records(
            [self._repair_record(blocked)], self.root,
            FileOperations.STRATEGIES[1], False, 1024,
            lambda _message: None, {".bad"},
        )
        self.assertEqual(0, result["renamed"])
        self.assertEqual(1, result["skipped"])
        self.assertTrue(blocked.exists())

    def test_restore_all_batches_and_changed_file_protection(self):
        operations = FileOperations(self.root / "operation_log.json")
        first = self.root / "first.bad"
        second = self.root / "second.bad"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        for source in (first, second):
            result = operations.rename_records(
                [self._repair_record(source)], self.root,
                FileOperations.STRATEGIES[1], False, 1024, lambda _message: None,
            )
            self.assertEqual(1, result["renamed"])

        preview, error = operations.preview_all_operations()
        self.assertFalse(error)
        self.assertEqual(2, len(preview))
        self.assertEqual((2, 0, ""), operations.undo_batch(None, lambda _message: None))
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

        changed = self.root / "changed.bad"
        changed.write_bytes(b"original")
        result = operations.rename_records(
            [self._repair_record(changed)], self.root,
            FileOperations.STRATEGIES[1], False, 1024, lambda _message: None,
        )
        self.assertEqual(1, result["renamed"])
        (self.root / "changed.png").write_bytes(b"different size and content")
        _batch, changed_preview, error = operations.preview_latest_batch()
        self.assertFalse(error)
        self.assertEqual("Blocked", changed_preview[0]["status"])
        self.assertIn("size changed", changed_preview[0]["detail"].lower())

    def test_undo_blocks_entries_without_a_recorded_scan_root(self):
        renamed = self.root / "unsafe.png"
        renamed.write_bytes(b"content")
        operation = {
            "source": str(self.root / "unsafe.bad"),
            "destination": str(renamed),
            "root_folder": "",
            "state": "completed",
            "size_bytes": renamed.stat().st_size,
        }
        operations = FileOperations(self.root / "operation_log.json")
        status, detail = operations.inspect_undo_operation(operation)
        self.assertEqual("Blocked", status)
        self.assertIn("scan folder", detail.lower())
        self.assertTrue(renamed.exists())

    def test_undo_blocks_resolved_parent_outside_recorded_root(self):
        scan_root = self.root / "scan_root"
        outside = self.root / "outside"
        scan_root.mkdir()
        outside.mkdir()
        linked_parent = scan_root / "linked"
        try:
            linked_parent.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symbolic links are unavailable")

        renamed = linked_parent / "linked.png"
        renamed.write_bytes(b"content")
        operation = {
            "source": str(linked_parent / "linked.bad"),
            "destination": str(renamed),
            "root_folder": str(scan_root),
            "state": "completed",
            "size_bytes": renamed.stat().st_size,
        }
        operations = FileOperations(self.root / "operation_log.json")
        status, detail = operations.inspect_undo_operation(operation)
        self.assertEqual("Blocked", status)
        self.assertIn("outside", detail.lower())
        self.assertTrue(renamed.exists())


if __name__ == "__main__":
    unittest.main()
