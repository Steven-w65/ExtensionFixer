# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Settings and undo-preview dialogs for the PyQt6 interface."""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .core import ApplicationSettings, MagicNumberDetector
from .core.operations import FileOperations
from .models import ModernCheckBox


class SettingsDialog(QDialog):
    """Single settings window containing preferences and format rules."""

    def __init__(
        self,
        settings: dict,
        store: ApplicationSettings,
        detector: MagicNumberDetector,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Extension Fixer Settings")
        self.setMinimumSize(780, 620)
        self.store = store
        self.detector = detector
        self.saved_settings: dict | None = None

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_general_tab(settings), "General and Scan")
        self.tabs.addTab(self._build_formats_tab(), "File Formats")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("quietButton")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        heading = QLabel("Settings", objectName="appTitle")
        heading.setStyleSheet("font-size: 17pt;")
        layout.addWidget(heading)
        layout.addWidget(QLabel(
            "Configure scanning, safety behavior, and format signatures.",
            objectName="dialogHint",
        ))
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

    def _build_general_tab(self, settings: dict) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Scan behavior", objectName="sectionTitle"))
        layout.addWidget(QLabel(
            "Choose what is scanned and what the results list displays.",
            objectName="dialogHint",
        ))
        form = QFormLayout()
        form.setContentsMargins(0, 6, 0, 0)
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.recursive = ModernCheckBox("Scan all subdirectories")
        self.recursive.setChecked(bool(settings["recursive_scan"]))
        self.repair_only = ModernCheckBox("Show only files requiring repair")
        self.repair_only.setChecked(bool(settings["show_only_repair_items"]))
        self.backup = ModernCheckBox("Back up original files before renaming")
        self.backup.setChecked(bool(settings["enable_backup"]))
        self.auto_scan_repair = ModernCheckBox("Automatic scan after repair")
        self.auto_scan_repair.setChecked(
            bool(settings["automatic_scan_after_repair"])
        )
        self.auto_scan_repair.setAccessibleName("Automatic scan after repair")
        self.auto_scan_repair.setToolTip(
            "Run a new scan after at least one file is successfully repaired."
        )
        self.auto_scan_undo = ModernCheckBox("Automatic scan after undo")
        self.auto_scan_undo.setChecked(bool(settings["automatic_scan_after_undo"]))
        self.auto_scan_undo.setAccessibleName("Automatic scan after undo")
        self.auto_scan_undo.setToolTip(
            "Run a new scan after an undo operation finishes."
        )

        self.strategy = QComboBox()
        for code, name in FileOperations.STRATEGIES.items():
            self.strategy.addItem(f"{code} - {name}", code)
        index = self.strategy.findData(int(settings["duplicate_strategy"]))
        self.strategy.setCurrentIndex(max(index, 0))

        self.size_limit = QDoubleSpinBox()
        self.size_limit.setRange(0, 1_000_000)
        self.size_limit.setDecimals(2)
        self.size_limit.setSuffix(" MB  (0 = unlimited)")
        self.size_limit.setValue(float(settings["max_size_mb"]))

        self.blacklist = QLineEdit(str(settings["suffix_blacklist"]))
        self.blacklist.setPlaceholderText(".exe, .dll")

        form.addRow(self.recursive)
        form.addRow(self.repair_only)
        form.addRow(self.backup)
        form.addRow(self.auto_scan_repair)
        form.addRow(self.auto_scan_undo)
        form.addRow("Duplicate strategy", self.strategy)
        form.addRow("Maximum file size", self.size_limit)
        form.addRow("Suffix blacklist", self.blacklist)
        layout.addLayout(form)
        layout.addStretch()
        return widget

    def _build_formats_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Magic-number formats", objectName="sectionTitle"))
        help_label = QLabel(
            "All format detection rules are stored here. Signatures must fit "
            "within the first 16 bytes. Saving validates every rule before replacing the file."
        )
        help_label.setObjectName("dialogHint")
        help_label.setWordWrap(True)
        self.format_editor = QTextEdit()
        self.format_editor.setAcceptRichText(False)
        self.format_editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        try:
            self.format_editor.setPlainText(
                self.detector.config_path.read_text(encoding="utf-8")
            )
        except OSError:
            self.format_editor.setPlainText('{\n  "formats": []\n}')

        validate = QPushButton("Validate Format Configuration")
        validate.setObjectName("quietButton")
        validate.clicked.connect(self._validate_formats)
        layout.addWidget(help_label)
        layout.addWidget(self.format_editor, 1)
        layout.addWidget(validate, alignment=Qt.AlignmentFlag.AlignLeft)
        return widget

    def _validate_formats(self) -> bool:
        try:
            configuration = json.loads(self.format_editor.toPlainText())
        except json.JSONDecodeError as error:
            QMessageBox.warning(self, "Invalid JSON", str(error))
            return False
        rules, errors = self.detector.parse_configuration(configuration)
        if errors:
            QMessageBox.warning(self, "Invalid Format Rules", "\n".join(errors))
            return False
        QMessageBox.information(self, "Configuration Valid", f"Validated {len(rules)} rule(s).")
        return True

    def _save(self):
        success, message = self.detector.save_text(self.format_editor.toPlainText())
        if not success:
            QMessageBox.warning(self, "Formats Not Saved", message)
            return
        settings = {
            "last_folder": str(self.parent().folder_edit.text()).strip(),
            "recursive_scan": self.recursive.isChecked(),
            "show_only_repair_items": self.repair_only.isChecked(),
            "enable_backup": self.backup.isChecked(),
            "automatic_scan_after_repair": self.auto_scan_repair.isChecked(),
            "automatic_scan_after_undo": self.auto_scan_undo.isChecked(),
            "duplicate_strategy": int(self.strategy.currentData()),
            "max_size_mb": f"{self.size_limit.value():g}",
            "suffix_blacklist": self.blacklist.text().strip(),
        }
        saved, error = self.store.save(settings)
        if not saved:
            QMessageBox.critical(self, "Settings Not Saved", error)
            return
        self.saved_settings = settings
        self.accept()


class UndoPreviewDialog(QDialog):
    """Read-only undo preview requiring a second explicit confirmation."""

    def __init__(self, preview: list[dict], scope_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Undo Preview — {scope_name}")
        self.setMinimumSize(850, 460)
        ready = sum(item["status"] == "Ready" for item in preview)

        label = QLabel(f"{scope_name}: {ready} of {len(preview)} item(s) are ready to restore.")
        table = QTableWidget(len(preview), 5)
        table.setHorizontalHeaderLabels(("Current Name", "Restore To", "Batch", "Status", "Details"))
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        for row, item in enumerate(preview):
            values = (
                item["current_name"],
                item["original_name"],
                item.get("batch_id", "latest"),
                item["status"],
                item["detail"],
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if item["status"] == "Ready":
                    cell.setBackground(QColor("#EAF6EC"))
                elif item["status"] == "Blocked":
                    cell.setBackground(QColor("#FDE7E4"))
                else:
                    cell.setBackground(QColor("#FFF1CC"))
                cell.setToolTip(str(value))
                table.setItem(row, column, cell)
        table.setColumnWidth(0, 180)
        table.setColumnWidth(1, 180)
        table.setColumnWidth(2, 170)
        table.setColumnWidth(3, 110)
        table.horizontalHeader().setStretchLastSection(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        restore = QPushButton(f"Restore {scope_name}")
        restore.setObjectName("dangerButton")
        restore.setEnabled(ready > 0)
        restore.clicked.connect(self.accept)
        buttons.addButton(restore, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(table, 1)
        layout.addWidget(buttons)
