# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QLabel,
    QMessageBox,
)

from extension_fixer import __version__, dialogs
from extension_fixer.core import FileScanner, MagicNumberDetector
from extension_fixer.dialogs import SettingsDialog, UndoPreviewDialog
from extension_fixer.main_window import MainWindow
from extension_fixer.models import RepairFilterModel, ScanResultModel
from extension_fixer.workers import ScanWorker


def make_record(index: int, status: str = "Repair required") -> dict:
    return {
        "path": f"C:/scan/file_{index}.bad",
        "relative_path": f"file_{index}.bad",
        "file_name": f"file_{index}.bad",
        "current_extension": ".bad",
        "detected_extension": ".png" if status == "Repair required" else "",
        "status": status,
        "size_bytes": 8,
        "size_display": "8 B",
        "planned_path": "",
        "error": "",
    }


class QtTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_model_incremental_insert_checkbox_and_proxy_filter(self):
        model = ScanResultModel()
        inserted = QSignalSpy(model.rowsInserted)
        reset = QSignalSpy(model.modelReset)
        model.append_records([make_record(index) for index in range(1000)])
        model.append_records([make_record(1000, "Normal: extension matches")])
        self.assertEqual(1001, model.rowCount())
        self.assertEqual(2, len(inserted))
        self.assertEqual(0, len(reset))

        index = model.index(0, 0)
        self.assertTrue(model.setData(index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole))
        self.assertEqual(1, len(model.checked_repair_records()))
        self.assertEqual(1, model.checked_repair_count())
        self.assertTrue(model.has_checked_repairs())

        proxy = RepairFilterModel()
        proxy.setSourceModel(model)
        self.assertEqual(1001, proxy.rowCount())
        self.assertEqual((1001, 1), proxy.selection_counts())
        proxy.set_repair_only(True)
        self.assertEqual(1000, proxy.rowCount())
        self.assertEqual((1000, 1), proxy.selection_counts())
        self.assertTrue(model.setData(
            index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole
        ))
        self.assertEqual((1000, 0), proxy.selection_counts())
        self.assertFalse(model.has_checked_repairs())

    def test_entire_checkbox_cell_toggles_once_per_click(self):
        """Repeated clicks anywhere in the cell must each toggle exactly once."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            record = make_record(123)
            window.model.append_records([record])
            window.show()
            self.app.processEvents()

            index = window.proxy.index(0, 0)
            cell = window.table.visualRect(index)
            # Exercise the native-indicator area plus both edges repeatedly.
            # The edges are deliberately outside the platform checkbox's own
            # small hit rectangle.
            click_points = (
                QPoint(cell.left() + 2, cell.center().y()),
                cell.center(),
                QPoint(cell.right() - 2, cell.center().y()),
            )
            with patch.object(
                window.model,
                "set_paths_checked",
                wraps=window.model.set_paths_checked,
            ) as shared_selection_method:
                for click_number in range(12):
                    QTest.mouseClick(
                        window.table.viewport(),
                        Qt.MouseButton.LeftButton,
                        pos=click_points[click_number % len(click_points)],
                    )
                    self.app.processEvents()
                    expected = {record["path"]} if click_number % 2 == 0 else set()
                    self.assertEqual(expected, window.model.checked_paths)

                self.assertEqual(12, shared_selection_method.call_count)
                self.assertTrue(all(
                    call.args[0] == {record["path"]}
                    for call in shared_selection_method.call_args_list
                ))

                # A real rapid second click is delivered by Qt as a distinct
                # double-click event, not as another normal press event.
                QTest.mouseClick(
                    window.table.viewport(),
                    Qt.MouseButton.LeftButton,
                    pos=cell.center(),
                )
                self.assertEqual({record["path"]}, window.model.checked_paths)
                QTest.mouseDClick(
                    window.table.viewport(),
                    Qt.MouseButton.LeftButton,
                    pos=cell.center(),
                )
                self.app.processEvents()
                self.assertEqual(set(), window.model.checked_paths)
                self.assertEqual(14, shared_selection_method.call_count)
            window.close()

    def test_scan_worker_batches_and_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "formats.json"
            config.write_text(json.dumps({"formats": [{
                "extension": "png", "offset": 0, "signature_hex": "89504E470D0A1A0A"
            }]}), encoding="utf-8")
            scan = root / "scan"
            scan.mkdir()
            for index in range(17):
                (scan / f"file_{index}.bad").write_bytes(bytes.fromhex("89504E470D0A1A0A"))
            detector = MagicNumberDetector(config)
            detector.load()
            worker = ScanWorker(FileScanner(detector), scan, False, 1024, set(), batch_size=5)
            batches = []
            completed = []
            worker.batchReady.connect(batches.append)
            worker.completed.connect(completed.append)
            worker.run()
            self.assertEqual(17, sum(len(batch) for batch in batches))
            self.assertEqual(17, completed[0]["processed"])

            cancelled_worker = ScanWorker(FileScanner(detector), scan, False, 1024, set())
            cancelled = []
            cancelled_worker.cancelled.connect(cancelled.append)
            cancelled_worker.request_cancel()
            cancelled_worker.run()
            self.assertEqual(0, cancelled[0]["processed"])

    def _prepare_window_folder(self, root: Path, count: int = 8):
        (root / "custom_magic_formats.json").write_text(json.dumps({"formats": [{
            "extension": "png", "offset": 0, "signature_hex": "89504E470D0A1A0A"
        }]}), encoding="utf-8")
        scan = root / "scan"
        scan.mkdir()
        for index in range(count):
            (scan / f"item_{index}.wrong").write_bytes(bytes.fromhex("89504E470D0A1A0A"))
        return scan

    def _wait_until(self, predicate, timeout_ms=5000):
        elapsed = 0
        while not predicate() and elapsed < timeout_ms:
            QTest.qWait(20)
            elapsed += 20
        self.assertTrue(predicate(), "Qt operation did not finish before timeout")

    def test_main_window_scan_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root)
            window = MainWindow(root)
            window.folder_edit.setText(str(scan))
            window.start_scan()
            self.assertIsNotNone(window.scan_thread)
            self._wait_until(lambda: window.scan_thread is None)
            self.assertEqual(8, window.model.rowCount())
            self.assertEqual(
                8,
                sum(record["status"] == "Repair required" for record in window.model.records),
            )
            self.assertEqual(set(), window.model.checked_paths)
            self.assertEqual("Scan Files", window.scan_button.text())
            window.close()

    def test_invalid_scan_folder_is_rejected_without_starting_thread(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.folder_edit.setText(str(root / "does-not-exist"))
            with patch("extension_fixer.main_window.QMessageBox.warning") as warning:
                window.start_scan()
            warning.assert_called_once()
            self.assertIsNone(window.scan_thread)
            self.assertIsNone(window.current_scan_root)
            window.close()

    def test_primary_controls_visible_at_minimum_window_sizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.resize(window.minimumSize())
            window.show()
            self.app.processEvents()

            main_controls = (
                window.settings_button,
                window.folder_edit,
                window.browse_button,
                window.scan_button,
                window.select_visible,
                window.count_label,
                window.progress,
                window.table,
                window.log_view,
                window.export_button,
                window.preview_button,
                window.repair_button,
                window.undo_button,
            )
            self.assertTrue(all(control.isVisible() for control in main_controls))
            self.assertTrue(all(
                button.height() >= 36
                for button in (
                    window.settings_button,
                    window.browse_button,
                    window.scan_button,
                    window.export_button,
                    window.preview_button,
                    window.repair_button,
                    window.undo_button,
                )
            ))

            dialog = SettingsDialog(
                window.settings, window.settings_store, window.detector, window
            )
            dialog.resize(dialog.minimumSize())
            dialog.show()
            self.app.processEvents()
            self.assertTrue(dialog.auto_scan_repair.isVisible())
            self.assertTrue(dialog.auto_scan_undo.isVisible())
            self.assertIsInstance(dialog.auto_scan_repair, QCheckBox)
            self.assertIsInstance(dialog.auto_scan_undo, QCheckBox)
            self.assertGreaterEqual(dialog.auto_scan_repair.height(), 28)
            self.assertEqual(
                window.select_visible.style().objectName(),
                dialog.auto_scan_repair.style().objectName(),
            )
            dialog.close()
            window.close()

    def test_window_version_badge_matches_package_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            badge = window.findChild(QLabel, "versionBadge")
            self.assertIsNotNone(badge)
            self.assertEqual(f"v{__version__}", badge.text())
            window.close()

    def test_repair_preview_dialog_is_large_and_lists_checked_files(self):
        self.assertTrue(
            hasattr(dialogs, "RepairPreviewDialog"),
            "Repair preview must use a dedicated readable dialog",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            first = make_record(1)
            first["path"] = "C:/scan/photos/holiday-photo.wrong"
            first["relative_path"] = "photos/holiday-photo.wrong"
            second = make_record(2)
            second["path"] = "C:/scan/archives/package.unknown"
            second["relative_path"] = "archives/package.unknown"
            window.model.append_records([first, second])
            window.model.set_paths_checked({first["path"], second["path"]}, True)

            captured_dialogs = []

            def capture_dialog(dialog):
                captured_dialogs.append(dialog)
                return dialog.DialogCode.Rejected

            with patch.object(dialogs.RepairPreviewDialog, "exec", capture_dialog):
                window.preview_repairs()

            self.assertEqual(1, len(captured_dialogs))
            preview = captured_dialogs[0]
            self.assertGreaterEqual(preview.minimumWidth(), 860)
            self.assertGreaterEqual(preview.minimumHeight(), 480)
            self.assertEqual(2, preview.table.rowCount())
            self.assertEqual(3, preview.table.columnCount())
            self.assertEqual(
                ["Selected File", "New Filename", "Status"],
                [preview.table.horizontalHeaderItem(column).text() for column in range(3)],
            )
            self.assertEqual("photos/holiday-photo.wrong", preview.table.item(0, 0).text())
            self.assertEqual("holiday-photo.png", preview.table.item(0, 1).text())
            self.assertEqual("Planned", preview.table.item(0, 2).text())
            self.assertIn("Planned: 2", preview.summary_label.text())
            self.assertEqual(
                QAbstractItemView.EditTrigger.NoEditTriggers,
                preview.table.editTriggers(),
            )
            window.close()

    def test_window_stop_waits_for_confirmed_thread_exit(self):
        class SlowScanner:
            @staticmethod
            def parse_blacklist(_text):
                return set()

            def scan_iter(self, *_args, cancelled=None, **_kwargs):
                cancel_callback = _args[-1] if _args and callable(_args[-1]) else cancelled
                for index in range(200):
                    if cancel_callback and cancel_callback():
                        return
                    time.sleep(0.003)
                    yield make_record(index)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.scanner = SlowScanner()
            window.folder_edit.setText(str(scan))
            window.start_scan()
            QTest.qWait(30)
            active_thread = window.scan_thread
            self.assertFalse(window.browse_button.isEnabled())
            window.stop_scan()
            self.assertIs(active_thread, window.scan_thread)
            self.assertFalse(window.scan_button.isEnabled())
            self._wait_until(lambda: window.scan_thread is None)
            self.assertTrue(window.scan_button.isEnabled())
            self.assertTrue(window.browse_button.isEnabled())
            self.assertEqual("Scan Files", window.scan_button.text())
            window.close()

    def test_operation_thread_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            received = []
            window._start_operation(
                "Testing operation",
                lambda logger: (logger("worker log"), 42)[1],
                received.append,
            )
            self.assertIsNotNone(window.operation_thread)
            self.assertFalse(window.undo_button.isEnabled())
            self._wait_until(lambda: window.operation_thread is None)
            self.assertEqual([42], received)
            self.assertTrue(window.undo_button.isEnabled())
            self.assertIn("worker log", window.log_view.toPlainText())
            window.close()

    def test_new_scan_clears_previous_checkbox_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root, 2)
            window = MainWindow(root)
            window.model.append_records([make_record(999)])
            window.model.set_paths_checked({"C:/scan/file_999.bad"}, True)
            self.assertTrue(window.model.checked_paths)
            window.folder_edit.setText(str(scan))
            window.start_scan()
            self.assertEqual(set(), window.model.checked_paths)
            self._wait_until(lambda: window.scan_thread is None)
            window.close()

    def test_threaded_repair_does_not_automatically_rescan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root, 1)
            source = scan / "item_0.wrong"
            target = scan / "item_0.png"
            window = MainWindow(root)
            window.settings["enable_backup"] = False
            window.folder_edit.setText(str(scan))
            window.start_scan()
            self._wait_until(lambda: window.scan_thread is None)
            self.assertTrue(source.exists())
            scanned_path = window.model.records[0]["path"]
            self.assertTrue(os.path.samefile(source, scanned_path))
            self.assertTrue(window.model.set_paths_checked({scanned_path}, True))
            self.assertEqual({scanned_path}, window.model.checked_paths)
            # Editing the path field after scanning must not redirect an
            # already-prepared repair operation to another folder.
            unrelated = root / "unrelated"
            unrelated.mkdir()
            window.folder_edit.setText(str(unrelated))

            with (
                patch("extension_fixer.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
                patch("extension_fixer.main_window.QMessageBox.information"),
                patch("extension_fixer.main_window.QMessageBox.warning"),
                patch.object(window, "start_scan", wraps=window.start_scan) as rescan,
            ):
                window.execute_repairs()
                self._wait_until(lambda: window.operation_thread is None)
                rescan.assert_not_called()
            self.assertFalse(source.exists())
            self.assertTrue(target.exists())
            self.assertEqual(set(), window.model.checked_paths)
            self.assertEqual("item_0.wrong", window.model.records[0]["file_name"])
            self.assertIn("Scan manually", window.statusBar().currentMessage())
            window.close()

    def test_settings_dialog_save_flow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            dialog = SettingsDialog(
                window.settings, window.settings_store, window.detector, window
            )
            dialog.recursive.setChecked(False)
            dialog.repair_only.setChecked(True)
            dialog.backup.setChecked(False)
            dialog.auto_scan_repair.click()
            dialog.auto_scan_undo.click()
            dialog.strategy.setCurrentIndex(dialog.strategy.findData(3))
            dialog.size_limit.setValue(256)
            dialog.blacklist.setText(".exe, dll, .tmp")
            dialog.format_editor.setPlainText(json.dumps({"formats": [{
                "extension": "pdf", "offset": 0, "signature_hex": "25504446"
            }]}))
            dialog._save()
            self.assertEqual(SettingsDialog.DialogCode.Accepted, dialog.result())
            loaded = window.settings_store.load()
            self.assertFalse(loaded["recursive_scan"])
            self.assertTrue(loaded["show_only_repair_items"])
            self.assertFalse(loaded["enable_backup"])
            self.assertTrue(loaded["automatic_scan_after_repair"])
            self.assertTrue(loaded["automatic_scan_after_undo"])
            self.assertEqual(3, loaded["duplicate_strategy"])
            self.assertEqual("256", loaded["max_size_mb"])
            self.assertEqual(".exe, dll, .tmp", loaded["suffix_blacklist"])
            rules, errors = window.detector.load()
            self.assertEqual([], errors)
            self.assertEqual("pdf", rules[0][0])
            window.close()

    def test_settings_dialog_rolls_back_formats_when_settings_save_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            original_configuration = window.detector.config_path.read_bytes()
            original_rules = list(window.detector.formats)
            dialog = SettingsDialog(
                window.settings, window.settings_store, window.detector, window
            )
            dialog.format_editor.setPlainText(json.dumps({"formats": [{
                "extension": "pdf", "offset": 0, "signature_hex": "25504446"
            }]}))

            real_replace = os.replace
            replace_calls = 0

            def fail_second_commit(source, destination):
                nonlocal replace_calls
                replace_calls += 1
                if replace_calls == 2:
                    raise OSError("forced settings commit failure")
                return real_replace(source, destination)

            with (
                patch(
                    "extension_fixer.core.settings.os.replace",
                    side_effect=fail_second_commit,
                ),
                patch("extension_fixer.dialogs.QMessageBox.critical"),
            ):
                dialog._save()

            self.assertEqual(original_configuration, window.detector.config_path.read_bytes())
            self.assertEqual(original_rules, window.detector.formats)
            self.assertIsNone(dialog.saved_settings)
            self.assertEqual(SettingsDialog.DialogCode.Rejected, dialog.result())
            dialog.close()
            window.close()

    def test_automatic_scan_checkboxes_control_completion_handlers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.folder_edit.setText(str(scan))
            repair_result = {"message": "", "renamed": 1, "skipped": 0, "failed": 0}

            with (
                patch("extension_fixer.main_window.QMessageBox.information"),
                patch("extension_fixer.main_window.QMessageBox.warning"),
                patch.object(window, "start_scan") as start_scan,
            ):
                window.settings["automatic_scan_after_repair"] = True
                window._repair_finished(repair_result)
                start_scan.assert_called_once_with()

                start_scan.reset_mock()
                window.settings["automatic_scan_after_undo"] = True
                window._undo_finished((1, 0, ""))
                start_scan.assert_called_once_with()
            window.close()

    def test_automatic_scan_after_undo_rejects_an_empty_folder_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.settings["automatic_scan_after_undo"] = True
            window.folder_edit.clear()
            try:
                with (
                    patch("extension_fixer.main_window.QMessageBox.information"),
                    patch("extension_fixer.main_window.QMessageBox.warning"),
                ):
                    window._undo_finished((1, 0, ""))
                self.assertIsNone(window.scan_thread)
                self.assertIn("Scan manually", window.statusBar().currentMessage())
            finally:
                if window.scan_thread is not None:
                    window.stop_scan()
                    self._wait_until(lambda: window.scan_thread is None)
                window.close()

    def test_automatic_scan_after_undo_requires_a_restored_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.settings["automatic_scan_after_undo"] = True
            window.folder_edit.setText(str(scan))
            try:
                with (
                    patch("extension_fixer.main_window.QMessageBox.information"),
                    patch("extension_fixer.main_window.QMessageBox.warning"),
                ):
                    window._undo_finished((0, 1, ""))
                self.assertIsNone(window.scan_thread)
                self.assertIn("Scan manually", window.statusBar().currentMessage())
            finally:
                if window.scan_thread is not None:
                    window.stop_scan()
                    self._wait_until(lambda: window.scan_thread is None)
                window.close()

    def test_automatic_scan_after_undo_rejects_an_unreadable_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.settings["automatic_scan_after_undo"] = True
            window.folder_edit.setText(str(scan))
            try:
                with (
                    patch(
                        "extension_fixer.core.scanner.os.scandir",
                        side_effect=PermissionError("access denied"),
                    ),
                    patch("extension_fixer.main_window.QMessageBox.information"),
                    patch("extension_fixer.main_window.QMessageBox.warning"),
                ):
                    window._undo_finished((1, 0, ""))
                self.assertIsNone(window.scan_thread)
                self.assertIn("Scan manually", window.statusBar().currentMessage())
            finally:
                if window.scan_thread is not None:
                    window.stop_scan()
                    self._wait_until(lambda: window.scan_thread is None)
                window.close()

    def test_check_all_visible_respects_repair_filter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.show()
            self.app.processEvents()
            self.assertFalse(window.select_visible.isEnabled())
            self.assertEqual(
                Qt.CheckState.Unchecked, window.select_visible.checkState()
            )

            repair = make_record(1)
            normal = make_record(2, "Normal: extension matches")
            window._append_scan_batch([repair, normal])
            window.proxy.set_repair_only(True)
            window._sync_visible_check_state()
            self.assertTrue(window.select_visible.isEnabled())
            header = window.table.horizontalHeader()
            self.assertIs(window.select_visible.parent(), header.viewport())
            self.assertEqual(
                header.sectionViewportPosition(0)
                + (header.sectionSize(0) - window.select_visible.width()) // 2,
                window.select_visible.x(),
            )

            header_click = QPoint(
                header.sectionViewportPosition(0) + header.sectionSize(0) - 2,
                header.height() // 2,
            )
            QTest.mouseClick(
                header.viewport(), Qt.MouseButton.LeftButton, pos=header_click,
            )
            self.assertEqual({repair["path"]}, window.model.checked_paths)
            self.assertEqual(Qt.CheckState.Checked, window.select_visible.checkState())
            QTest.mouseClick(
                window.select_visible, Qt.MouseButton.LeftButton,
                pos=window.select_visible.rect().center(),
            )
            self.assertEqual(set(), window.model.checked_paths)
            self.assertEqual(Qt.CheckState.Unchecked, window.select_visible.checkState())

            # In a partial state, one click must select everything directly;
            # the aggregate display must never advance one state ahead.
            window.proxy.set_repair_only(False)
            window.model.set_paths_checked({repair["path"]}, True)
            self.assertEqual(
                Qt.CheckState.PartiallyChecked, window.select_visible.checkState()
            )
            QTest.mouseClick(
                window.select_visible, Qt.MouseButton.LeftButton,
                pos=window.select_visible.rect().center(),
            )
            self.assertEqual(
                {repair["path"], normal["path"]}, window.model.checked_paths
            )
            self.assertEqual(Qt.CheckState.Checked, window.select_visible.checkState())
            window.close()

    def test_threaded_csv_export_ui_flow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.model.append_records([make_record(7)])
            report = root / "ui_report.csv"
            with (
                patch(
                    "extension_fixer.main_window.QFileDialog.getSaveFileName",
                    return_value=(str(report), "CSV Files (*.csv)"),
                ),
                patch("extension_fixer.main_window.QMessageBox.information"),
            ):
                window.export_csv()
                self._wait_until(lambda: window.operation_thread is None)
            self.assertTrue(report.exists())
            self.assertIn("file_7.bad", report.read_text(encoding="utf-8-sig"))
            window.close()

    def test_latest_undo_preview_confirmation_ui_flow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = self._prepare_window_folder(root, 0)
            source = scan / "undo.bad"
            source.write_bytes(bytes.fromhex("89504E470D0A1A0A"))
            window = MainWindow(root)
            window.folder_edit.setText(str(scan))
            record = {
                "path": str(source), "relative_path": source.name,
                "file_name": source.name, "current_extension": ".bad",
                "detected_extension": ".png", "status": "Repair required",
                "size_bytes": source.stat().st_size, "size_display": "",
                "planned_path": "", "error": "",
            }
            result = window.operations.rename_records(
                [record], scan, "Auto append serial number", False, 1024,
                lambda _message: None,
            )
            self.assertEqual(1, result["renamed"])
            target = scan / "undo.png"
            with (
                patch.object(
                    UndoPreviewDialog, "exec",
                    return_value=UndoPreviewDialog.DialogCode.Accepted,
                ),
                patch(
                    "extension_fixer.main_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ),
                patch("extension_fixer.main_window.QMessageBox.information"),
                patch("extension_fixer.main_window.QMessageBox.warning"),
                patch.object(window, "start_scan", wraps=window.start_scan) as rescan,
            ):
                window.preview_undo_scope(False)
                self._wait_until(lambda: window.operation_thread is None)
                rescan.assert_not_called()
            self.assertTrue(source.exists())
            self.assertFalse(target.exists())
            self.assertIn("Scan manually", window.statusBar().currentMessage())
            window.close()

    def test_close_waits_for_operation_without_callback_dialog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_window_folder(root, 0)
            window = MainWindow(root)
            window.show()
            callbacks = []
            window._start_operation(
                "Slow operation",
                lambda _logger: (time.sleep(0.08), "done")[1],
                callbacks.append,
            )
            window.close()
            self.assertTrue(window.close_pending)
            self.assertIsNotNone(window.operation_thread)
            self._wait_until(lambda: window.operation_thread is None)
            self.assertEqual([], callbacks)
            self.assertFalse(window.isVisible())


if __name__ == "__main__":
    unittest.main()
