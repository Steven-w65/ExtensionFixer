# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""PyQt6 main window."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtGui import QCloseEvent, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .core import (
    ApplicationSettings,
    FileOperations,
    FileScanner,
    MagicNumberDetector,
    export_csv_report,
)
from .dialogs import RepairPreviewDialog, SettingsDialog, UndoPreviewDialog
from .models import (
    AggregateSelectionCheckBox,
    CenteredCheckBoxDelegate,
    CheckBoxHeaderView,
    CheckableResultTable,
    RepairFilterModel,
    ScanResultModel,
)
from .styles import APP_STYLE
from .workers import OperationWorker, ScanWorker


class MainWindow(QMainWindow):
    """Responsive, checkbox-driven Extension Fixer interface."""

    def __init__(self, data_dir: Path | str):
        super().__init__()
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.settings_store = ApplicationSettings(self.data_dir / "settings.json")
        self.settings = self.settings_store.load()
        self.detector = MagicNumberDetector(self.data_dir / "custom_magic_formats.json")
        self.scanner = FileScanner(self.detector)
        self.operations = FileOperations(
            self.data_dir / "operation_log.json", self.detector
        )

        self.scan_thread: QThread | None = None
        self.scan_worker: ScanWorker | None = None
        self.scan_summary: tuple[str, dict] | None = None
        self.scan_error = ""
        self.stop_requested = False
        self.operation_thread: QThread | None = None
        self.operation_worker: OperationWorker | None = None
        self.operation_result = None
        self.operation_error = ""
        self.operation_callback = None
        self.close_pending = False
        self.settings_dialog: SettingsDialog | None = None
        self.repair_count = 0
        self.current_scan_root: Path | None = None

        self.setWindowTitle("Extension Fixer")
        self.setMinimumSize(920, 650)
        self.resize(1280, 820)
        self.setStyleSheet(APP_STYLE)
        icon = self._resource_path("app.ico")
        if icon and icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self._build_ui()
        self._load_formats()
        self._update_actions()

    def _resource_path(self, name: str) -> Path | None:
        local = self.data_dir / name
        if local.exists():
            return local
        return None

    def _build_ui(self):
        central = QWidget(objectName="appSurface")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)
        self.setCentralWidget(central)

        header = QHBoxLayout()
        header.setSpacing(12)
        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = QLabel("Extension Fixer", objectName="appTitle")
        subtitle = QLabel(
            "Safe, signature-based extension repair",
            objectName="appSubtitle",
        )
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        version = QLabel("v2.0", objectName="versionBadge")
        header.addWidget(version)
        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("quietButton")
        self.settings_button.setToolTip("Open scan, repair, and format settings")
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.settings_button)
        outer.addLayout(header)

        path_panel = QFrame(objectName="card")
        path_layout = QVBoxLayout(path_panel)
        path_layout.setContentsMargins(16, 12, 16, 14)
        path_layout.setSpacing(7)
        path_layout.addWidget(QLabel("SCAN LOCATION", objectName="sectionCaption"))
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.folder_edit = QLineEdit(str(self.settings["last_folder"]))
        self.folder_edit.setPlaceholderText("Select a folder to scan")
        self.folder_edit.setClearButtonEnabled(True)
        self.browse_button = QPushButton("Browse…")
        self.browse_button.setToolTip("Choose a folder")
        self.browse_button.clicked.connect(self.browse_folder)
        self.scan_button = QPushButton("Scan Files")
        self.scan_button.setObjectName("primaryButton")
        self.scan_button.setToolTip("Scan the selected folder")
        self.scan_button.clicked.connect(self.start_scan)
        path_row.addWidget(self.folder_edit, 1)
        path_row.addWidget(self.browse_button)
        path_row.addWidget(self.scan_button)
        path_layout.addLayout(path_row)
        outer.addWidget(path_panel)

        self.select_visible = AggregateSelectionCheckBox()
        self.select_visible.setTristate(True)
        self.select_visible.setToolTip("Check or uncheck every currently displayed file")
        self.select_visible.activationRequested.connect(self.toggle_visible_checks)
        self.count_label = QLabel("Scanned: 0 · Repair candidates: 0 · Displayed: 0")
        self.count_label.setObjectName("metricsLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMinimumWidth(110)
        self.progress.setMaximumWidth(180)

        self.model = ScanResultModel(self)
        self.proxy = RepairFilterModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.set_repair_only(bool(self.settings["show_only_repair_items"]))
        self.model.checkedChanged.connect(self._checked_changed)
        self.model.modelReset.connect(self._update_counts)

        self.table = CheckableResultTable()
        self.table.setObjectName("resultsTable")
        self.table.setModel(self.proxy)
        self.result_header = CheckBoxHeaderView(self.select_visible, self.table)
        self.table.setHorizontalHeader(self.result_header)
        self.checkbox_delegate = CenteredCheckBoxDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.checkbox_delegate)
        self.table.checkboxPressed.connect(self.toggle_file_check)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._resize_table_columns()

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("activityLog")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.log_view.setPlaceholderText("Scan and file-operation messages appear here")
        self.log_view.setMinimumHeight(92)

        results_card = QFrame(objectName="resultsCard")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)
        results_toolbar = QWidget(objectName="resultsToolbar")
        results_toolbar_layout = QHBoxLayout(results_toolbar)
        results_toolbar_layout.setContentsMargins(16, 9, 14, 9)
        results_toolbar_layout.setSpacing(10)
        results_toolbar_layout.addWidget(QLabel("Scan results", objectName="sectionTitle"))
        results_toolbar_layout.addWidget(self.count_label)
        results_toolbar_layout.addStretch()
        results_toolbar_layout.addWidget(self.progress)
        results_layout.addWidget(results_toolbar)
        results_layout.addWidget(self.table, 1)

        activity_card = QFrame(objectName="activityCard")
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(0, 0, 0, 0)
        activity_layout.setSpacing(0)
        activity_header = QWidget(objectName="activityHeader")
        activity_header_layout = QHBoxLayout(activity_header)
        activity_header_layout.setContentsMargins(16, 8, 16, 8)
        activity_header_layout.addWidget(QLabel("Activity", objectName="sectionTitle"))
        activity_header_layout.addSpacing(8)
        activity_header_layout.addWidget(
            QLabel("Latest scan and file-operation messages", objectName="activityHint")
        )
        activity_header_layout.addStretch()
        activity_layout.addWidget(activity_header)
        activity_layout.addWidget(self.log_view, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(results_card)
        splitter.addWidget(activity_card)
        splitter.setSizes([540, 160])
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_button = QPushButton("Export CSV")
        self.export_button.setObjectName("quietButton")
        self.export_button.setToolTip("Export every current scan result to a CSV report")
        self.export_button.clicked.connect(self.export_csv)
        self.preview_button = QPushButton("Preview Repairs")
        self.preview_button.setToolTip("Preview renames for checked repair candidates")
        self.preview_button.clicked.connect(self.preview_repairs)
        self.repair_button = QPushButton("Execute Repair")
        self.repair_button.setObjectName("dangerButton")
        self.repair_button.setToolTip("Rename the checked repair candidates")
        self.repair_button.clicked.connect(self.execute_repairs)
        self.undo_button = QPushButton("Undo Recorded Changes")
        self.undo_button.setObjectName("quietButton")
        self.undo_button.setToolTip("Preview and restore recorded rename operations")
        self.undo_button.clicked.connect(self.undo_changes)
        actions.addWidget(self.export_button)
        actions.addStretch()
        actions.addWidget(self.undo_button)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.repair_button)
        outer.addLayout(actions)

        self.statusBar().showMessage("Ready")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "table"):
            self._resize_table_columns()

    def _resize_table_columns(self):
        """Fit every result column inside the current viewport at any DPI."""
        available = max(700, self.table.viewport().width())
        checkbox_width = 42
        current_width = 135
        detected_width = 150
        flexible = max(360, available - checkbox_width - current_width - detected_width - 4)
        file_width = max(220, int(flexible * 0.57))
        status_width = max(140, flexible - file_width)
        for column, width in enumerate((
            checkbox_width, file_width, current_width, detected_width, status_width
        )):
            self.table.setColumnWidth(column, width)

    def log(self, message: str):
        self.log_view.appendPlainText(str(message).rstrip())

    def _load_formats(self) -> bool:
        rules, errors = self.detector.load()
        for error in errors:
            self.log(f"Format warning: {error}")
        if rules:
            self.log(f"Loaded {len(rules)} magic-number rule(s).")
            return True
        return False

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", self.folder_edit.text() or str(Path.home())
        )
        if folder:
            self.folder_edit.setText(folder)

    @staticmethod
    def _accessible_scan_root(folder_text: str) -> Path | None:
        """Resolve a directory and verify that traversal can actually start."""
        if not folder_text:
            return None
        try:
            root = Path(folder_text).expanduser().resolve()
            if not root.is_dir():
                return None
            with os.scandir(root):
                pass
            return root
        except (OSError, RuntimeError, ValueError):
            return None

    def open_settings(self):
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        dialog = SettingsDialog(self.settings, self.settings_store, self.detector, self)
        self.settings_dialog = dialog
        if dialog.exec() == SettingsDialog.DialogCode.Accepted and dialog.saved_settings:
            self.settings = dialog.saved_settings
            self.proxy.set_repair_only(bool(self.settings["show_only_repair_items"]))
            self._update_counts()
            self._sync_visible_check_state()
            self.log("Settings and format rules saved.")
        self.settings_dialog = None

    def start_scan(self):
        if self.scan_thread is not None or self.operation_thread is not None:
            return
        folder_text = self.folder_edit.text().strip()
        root = self._accessible_scan_root(folder_text)
        if root is None:
            QMessageBox.warning(self, "Invalid Folder", "Select an existing folder first.")
            return
        self.folder_edit.setText(str(root))
        if not self._load_formats():
            QMessageBox.critical(self, "No Format Rules", "No valid magic-number rules are loaded.")
            return

        self.settings["last_folder"] = str(root)
        saved, save_error = self.settings_store.save(self.settings)
        if not saved:
            self.log(f"Warning: could not save the last folder: {save_error}")
        self.repair_count = 0
        self.model.clear()
        self.current_scan_root = root
        self.select_visible.setCheckState(Qt.CheckState.Unchecked)
        self.scan_summary = None
        self.scan_error = ""
        self.stop_requested = False
        self.progress.setRange(0, 0)
        self.scan_button.setText("Stop Scan")
        self.scan_button.setObjectName("dangerButton")
        self.scan_button.style().unpolish(self.scan_button)
        self.scan_button.style().polish(self.scan_button)
        try:
            max_size = float(self.settings["max_size_mb"])
        except (TypeError, ValueError):
            max_size = 1024.0
        blacklist = self.scanner.parse_blacklist(str(self.settings["suffix_blacklist"]))

        thread = QThread(self)
        worker = ScanWorker(
            self.scanner,
            root,
            bool(self.settings["recursive_scan"]),
            max_size,
            blacklist,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.batchReady.connect(self._append_scan_batch)
        worker.progress.connect(self._scan_progress)
        worker.logMessage.connect(self.log)
        worker.completed.connect(lambda summary: self._store_scan_summary("completed", summary))
        worker.cancelled.connect(lambda summary: self._store_scan_summary("cancelled", summary))
        worker.failed.connect(self._store_scan_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._scan_finished(thread))
        thread.finished.connect(thread.deleteLater)
        self.scan_thread = thread
        self.scan_worker = worker
        self.scan_button.clicked.disconnect()
        self.scan_button.clicked.connect(self.stop_scan)
        self.statusBar().showMessage(f"Scanning {root}")
        self.log(f"Scanning folder: {root}")
        self._update_actions()
        thread.start()

    def stop_scan(self):
        if self.scan_worker is None or self.stop_requested:
            return
        self.stop_requested = True
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Stopping…")
        self.statusBar().showMessage("Waiting for scanner thread to stop safely…")
        self.log("Stop requested; waiting for confirmed worker termination.")
        self.scan_worker.request_cancel()
        self._update_actions()

    def _store_scan_summary(self, outcome: str, summary: dict):
        self.scan_summary = (outcome, summary)

    def _store_scan_error(self, error: str):
        self.scan_error = error

    def _append_scan_batch(self, records: list[dict]):
        """Insert one worker batch and update counts without rescanning old rows."""
        self.model.append_records(records)
        self.repair_count += sum(
            record.get("status") == "Repair required" for record in records
        )
        self._update_counts()
        # Count-based synchronization stays constant-time even for huge scans.
        self._sync_visible_check_state()

    def _scan_progress(self, processed: int, repairs: int):
        self.repair_count = repairs
        self.count_label.setText(
            f"Scanned: {processed:,} · Repair candidates: {repairs:,} · "
            f"Displayed: {self.proxy.rowCount():,}"
        )

    def _scan_finished(self, expected_thread: QThread):
        if expected_thread is not self.scan_thread:
            return
        self.scan_thread = None
        self.scan_worker = None
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan Files")
        self.scan_button.setObjectName("primaryButton")
        self.scan_button.style().unpolish(self.scan_button)
        self.scan_button.style().polish(self.scan_button)
        self.scan_button.clicked.disconnect()
        self.scan_button.clicked.connect(self.start_scan)
        self.stop_requested = False

        if self.close_pending:
            if self.scan_error:
                self.log(self.scan_error)
            else:
                self.log("Scanner thread stopped; closing application.")
            self.close()
            return

        if self.scan_error:
            self.log(self.scan_error)
            QMessageBox.critical(self, "Scan Failed", self.scan_error)
            self.statusBar().showMessage("Scan failed")
        else:
            outcome, summary = self.scan_summary or ("cancelled", {
                "processed": len(self.model.records),
                "repair_count": sum(
                    record.get("status") == "Repair required" for record in self.model.records
                ),
            })
            message = (
                f"Scan {outcome}: {summary['processed']:,} checked; "
                f"{summary['repair_count']:,} require repair."
            )
            self.log(message)
            self.statusBar().showMessage(message)
        self._update_counts()
        self._update_actions()

    def _checked_changed(self, _count: int):
        self._sync_visible_check_state()
        self._update_actions()

    def _sync_visible_check_state(self):
        """Reflect none/all/partial checkbox state for current proxy rows."""
        visible_count, selected_count = self.proxy.selection_counts()
        self.select_visible.blockSignals(True)
        if selected_count == 0:
            self.select_visible.setCheckState(Qt.CheckState.Unchecked)
        elif selected_count == visible_count:
            self.select_visible.setCheckState(Qt.CheckState.Checked)
        else:
            self.select_visible.setCheckState(Qt.CheckState.PartiallyChecked)
        self.select_visible.blockSignals(False)
        self._update_select_visible_enabled()

    def _update_select_visible_enabled(self):
        """Enable aggregate selection only when it can affect visible rows."""
        has_visible_rows = self.proxy.rowCount() > 0
        available = self.operation_thread is None and not self.stop_requested
        self.select_visible.setEnabled(has_visible_rows and available)

    def toggle_visible_checks(self):
        visible = self.proxy.visible_paths()
        all_checked = bool(visible) and visible.issubset(self.model.checked_paths)
        self.model.set_paths_checked(visible, not all_checked)

    def toggle_file_check(self, proxy_index):
        """Toggle one file through the same path used by the overall checkbox."""
        source_index = self.proxy.mapToSource(proxy_index)
        if not source_index.isValid() or source_index.row() >= len(self.model.records):
            return
        path = self.model.records[source_index.row()].get("path", "")
        if path:
            self.model.set_paths_checked(
                {path}, path not in self.model.checked_paths
            )

    def _update_counts(self):
        self.count_label.setText(
            f"Scanned: {len(self.model.records):,} · Repair candidates: {self.repair_count:,} · "
            f"Displayed: {self.proxy.rowCount():,}"
        )

    def _update_actions(self):
        busy = self.scan_thread is not None or self.operation_thread is not None
        selected = self.model.has_checked_repairs()
        self.settings_button.setEnabled(not busy)
        self.folder_edit.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.preview_button.setEnabled(selected and not busy)
        self.repair_button.setEnabled(selected and not busy)
        self.undo_button.setEnabled(not busy)
        self.export_button.setEnabled(bool(self.model.records) and not busy)
        self._update_select_visible_enabled()
        if self.scan_thread is None:
            self.scan_button.setEnabled(self.operation_thread is None)

    def preview_repairs(self):
        records = [dict(record) for record in self.model.checked_repair_records()]
        if not records:
            return
        strategy = FileOperations.STRATEGIES[int(self.settings["duplicate_strategy"])]
        planned, conflicts, error = self.operations.plan_renames(records, strategy)
        if error:
            QMessageBox.warning(self, "Preview Blocked", error)
            return
        skipped = len(records) - len(planned)
        planned_targets = {
            str(source): target for _record, source, target in planned
        }
        conflict_targets = set(conflicts)
        rows = []
        for record in records:
            source = Path(str(record.get("path", "")))
            target = planned_targets.get(str(source))
            if target is None:
                new_filename = "—"
                status = "Skipped"
            else:
                new_filename = target.name
                initial_target = source.with_suffix(
                    str(record.get("detected_extension", ""))
                )
                status = (
                    "Conflict resolved"
                    if str(initial_target) in conflict_targets
                    else "Planned"
                )
            rows.append({
                "selected_file": str(record.get("relative_path", source.name)),
                "new_filename": new_filename,
                "status": status,
            })

        dialog = RepairPreviewDialog(
            rows,
            planned=len(planned),
            skipped=skipped,
            conflicts=len(conflicts),
            parent=self,
        )
        dialog.exec()

    def execute_repairs(self):
        selected = [dict(record) for record in self.model.checked_repair_records()]
        if not selected:
            return
        root = self.current_scan_root
        if root is None:
            QMessageBox.warning(self, "Repair Blocked", "Run a scan before repairing files.")
            return
        try:
            if not root.is_dir():
                raise OSError("the scanned folder no longer exists")
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.warning(self, "Repair Blocked", f"Cannot access the scanned folder:\n{error}")
            return
        strategy = FileOperations.STRATEGIES[int(self.settings["duplicate_strategy"])]
        backup = bool(self.settings["enable_backup"])
        try:
            max_size = float(self.settings["max_size_mb"])
        except (TypeError, ValueError):
            max_size = 1024.0
        blacklist = self.scanner.parse_blacklist(
            str(self.settings["suffix_blacklist"])
        )
        answer = QMessageBox.question(
            self,
            "Confirm File Rename",
            f"Rename {len(selected)} checked file(s)?\n\n"
            f"Strategy: {strategy}\nBackup: {'enabled' if backup else 'disabled'}\n\n"
            "Only file names will be changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def task(logger):
            return self.operations.rename_records(
                selected, root, strategy, backup, max_size, logger, blacklist
            )

        self._start_operation("Repairing files", task, self._repair_finished)

    def _repair_finished(self, result: dict):
        if result.get("message"):
            QMessageBox.warning(self, "Repair Not Completed", result["message"])
            return
        auto_scan = (
            bool(self.settings.get("automatic_scan_after_repair", False))
            and bool(result.get("renamed"))
        )
        refresh_note = (
            "The results will now be scanned automatically."
            if auto_scan
            else "Click Scan Files when you want to refresh the results."
        )
        QMessageBox.information(
            self,
            "Repair Complete",
            f"Renamed: {result['renamed']}\nSkipped: {result['skipped']}\nFailed: {result['failed']}\n\n"
            f"{refresh_note}",
        )
        self.model.set_paths_checked(set(self.model.checked_paths), False)
        if auto_scan:
            self.log("Repair complete; starting the enabled automatic scan.")
            self.start_scan()
        else:
            self.statusBar().showMessage("Repair complete · Scan manually to refresh results")
            self.log("Automatic scan after repair is disabled; click Scan Files to refresh.")

    def export_csv(self):
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, "Export Scan Report", str(Path(self.folder_edit.text() or self.data_dir) / "extensionfixer_report.csv"),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        records = [dict(record) for record in self.model.records]

        def task(_logger):
            return export_csv_report(records, path)

        self._start_operation("Exporting CSV", task, lambda result: QMessageBox.information(
            self, "Export Complete", f"Report saved to:\n{result}"
        ))

    def undo_changes(self):
        choice = QMessageBox(self)
        choice.setWindowTitle("Choose Undo Scope")
        choice.setText("Which recorded operations do you want to preview?")
        latest_button = choice.addButton("Latest Batch", QMessageBox.ButtonRole.AcceptRole)
        all_button = choice.addButton("All Recorded", QMessageBox.ButtonRole.ActionRole)
        choice.addButton(QMessageBox.StandardButton.Cancel)
        choice.exec()
        clicked = choice.clickedButton()
        if clicked not in (latest_button, all_button):
            return

        self.preview_undo_scope(clicked is all_button)

    def preview_undo_scope(self, restore_all: bool):
        """Open and execute a confirmed latest/all undo workflow."""
        if restore_all:
            preview, error = self.operations.preview_all_operations()
            batch_id = None
            scope = "All Recorded"
        else:
            batch_id, preview, error = self.operations.preview_latest_batch()
            scope = "Latest Batch"
        if error:
            QMessageBox.warning(self, "Undo Unavailable", error)
            return
        dialog = UndoPreviewDialog(preview, scope, self)
        if dialog.exec() != UndoPreviewDialog.DialogCode.Accepted:
            return
        confirmed = QMessageBox.question(
            self, "Confirm Undo", f"Restore all Ready entries in {scope.lower()}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        self._start_operation(
            "Restoring file names",
            lambda logger: self.operations.undo_batch(batch_id, logger),
            self._undo_finished,
        )

    def _undo_finished(self, result):
        undone, failed, message = result
        folder_text = self.folder_edit.text().strip()
        folder_is_valid = self._accessible_scan_root(folder_text) is not None
        auto_scan = (
            bool(self.settings.get("automatic_scan_after_undo", False))
            and undone > 0
            and folder_is_valid
        )
        refresh_note = (
            "The results will now be scanned automatically."
            if auto_scan
            else "Click Scan Files when you want to refresh the results."
        )
        if message:
            QMessageBox.warning(self, "Undo Warning", message)
        else:
            QMessageBox.information(
                self,
                "Undo Complete",
                f"Restored: {undone}\nCould not restore: {failed}\n\n"
                f"{refresh_note}",
            )
        self.model.set_paths_checked(set(self.model.checked_paths), False)
        if auto_scan:
            self.log("Undo complete; starting the enabled automatic scan.")
            self.start_scan()
        else:
            self.statusBar().showMessage("Undo complete · Scan manually to refresh results")
            self.log("Automatic scan after undo is disabled; click Scan Files to refresh.")

    def _start_operation(self, label: str, task, callback):
        if self.scan_thread is not None or self.operation_thread is not None:
            return
        thread = QThread(self)
        worker = OperationWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.logMessage.connect(self.log)
        worker.succeeded.connect(self._store_operation_result)
        worker.failed.connect(self._store_operation_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._operation_finished(thread))
        thread.finished.connect(thread.deleteLater)
        self.operation_result = None
        self.operation_error = ""
        self.operation_callback = callback
        self.operation_thread = thread
        self.operation_worker = worker
        self.progress.setRange(0, 0)
        self.statusBar().showMessage(label)
        self._update_actions()
        thread.start()

    def _store_operation_result(self, result):
        self.operation_result = result

    def _store_operation_error(self, error: str):
        self.operation_error = error

    def _operation_finished(self, expected_thread: QThread):
        if expected_thread is not self.operation_thread:
            return
        callback = self.operation_callback
        result = self.operation_result
        error = self.operation_error
        self.operation_thread = None
        self.operation_worker = None
        self.operation_callback = None
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.statusBar().showMessage("Ready")
        self._update_actions()
        if self.close_pending:
            if error:
                self.log(error)
            self.close()
            return
        if error:
            self.log(error)
            QMessageBox.critical(self, "Operation Failed", error)
        elif callback:
            callback(result)

    def closeEvent(self, event: QCloseEvent):
        if self.scan_thread is not None:
            self.close_pending = True
            self.stop_scan()
            event.ignore()
            return
        if self.operation_thread is not None:
            self.close_pending = True
            self.statusBar().showMessage("Waiting for file operation to finish safely…")
            event.ignore()
            return
        self.settings["last_folder"] = self.folder_edit.text().strip()
        self.settings_store.save(self.settings)
        event.accept()
