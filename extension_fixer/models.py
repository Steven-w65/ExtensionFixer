# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Qt models for large, incrementally updated scan results."""

from __future__ import annotations

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QRect,
    QRectF,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
)


CHECKBOX_INDICATOR_SIZE = 16


def paint_checkbox_indicator(
    painter: QPainter,
    rect: QRect,
    state: Qt.CheckState,
    enabled: bool = True,
    hovered: bool = False,
):
    """Paint the single checkbox design shared by every application surface."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QRectF(rect).adjusted(0.75, 0.75, -0.75, -0.75)

    if not enabled:
        border = QColor("#B8C2CF")
        fill = QColor("#E8EDF3")
    elif state in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked):
        border = QColor("#2563EB")
        fill = QColor("#2563EB")
    else:
        border = QColor("#3B82F6") if hovered else QColor("#94A3B8")
        fill = QColor("#FFFFFF")

    painter.setPen(QPen(border, 1.4))
    painter.setBrush(fill)
    painter.drawRoundedRect(box, 4.0, 4.0)

    if state == Qt.CheckState.Checked:
        painter.setPen(QPen(
            QColor("#FFFFFF") if enabled else QColor("#8A98AA"),
            2.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        path = QPainterPath()
        path.moveTo(box.left() + 3.2, box.top() + 7.7)
        path.lineTo(box.left() + 6.4, box.top() + 10.7)
        path.lineTo(box.left() + 12.2, box.top() + 4.7)
        painter.drawPath(path)
    elif state == Qt.CheckState.PartiallyChecked:
        painter.setPen(QPen(
            QColor("#FFFFFF") if enabled else QColor("#8A98AA"),
            2.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        ))
        middle = box.center().y()
        painter.drawLine(
            int(box.left() + 4.0), int(middle),
            int(box.right() - 4.0), int(middle),
        )
    painter.restore()


class ModernCheckBox(QCheckBox):
    """Standard interactive checkbox using the shared application indicator."""

    def paintEvent(self, _event):
        painter = QPainter(self)
        indicator_size = CHECKBOX_INDICATOR_SIZE
        if self.text():
            indicator = QRect(
                0,
                (self.height() - indicator_size) // 2,
                indicator_size,
                indicator_size,
            )
        else:
            indicator = QRect(
                (self.width() - indicator_size) // 2,
                (self.height() - indicator_size) // 2,
                indicator_size,
                indicator_size,
            )
        paint_checkbox_indicator(
            painter,
            indicator,
            self.checkState(),
            self.isEnabled(),
            self.underMouse(),
        )

        if self.text():
            text_rect = self.rect().adjusted(indicator_size + 9, 0, 0, 0)
            self.style().drawItemText(
                painter,
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self.palette(),
                self.isEnabled(),
                self.text(),
            )
        if self.hasFocus():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#93C5FD"), 1.0, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(
                0.5, 0.5, -0.5, -0.5
            ), 5.0, 5.0)


class AggregateSelectionCheckBox(ModernCheckBox):
    """Three-state display whose state is owned exclusively by the model.

    QCheckBox normally advances its own state before emitting ``clicked``.
    That creates a transient one-step offset for an aggregate checkbox. This
    subclass reports the activation without changing its display; the main
    window changes the model and then derives the correct display state.
    """

    activationRequested = pyqtSignal()

    def nextCheckState(self):
        self.activationRequested.emit()


class CenteredCheckBoxDelegate(QStyledItemDelegate):
    """Paint first-column native checkboxes at the exact cell center."""

    def paint(self, painter, option, index):
        if index.column() != 0:
            super().paint(painter, option, index)
            return

        style = option.widget.style() if option.widget else QApplication.style()

        # Draw the normal cell background while suppressing Qt's default
        # leading-position checkbox. Interaction is owned by the table view.
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        item_option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        item_option.text = ""
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            item_option,
            painter,
            option.widget,
        )

        state = index.data(Qt.ItemDataRole.CheckStateRole)
        indicator = QRect(
            option.rect.x() + (option.rect.width() - CHECKBOX_INDICATOR_SIZE) // 2,
            option.rect.y() + (option.rect.height() - CHECKBOX_INDICATOR_SIZE) // 2,
            CHECKBOX_INDICATOR_SIZE,
            CHECKBOX_INDICATOR_SIZE,
        )
        paint_checkbox_indicator(
            painter,
            indicator,
            state if isinstance(state, Qt.CheckState) else Qt.CheckState(state),
            bool(option.state & QStyle.StateFlag.State_Enabled),
            bool(option.state & QStyle.StateFlag.State_MouseOver),
        )


class CheckBoxHeaderView(QHeaderView):
    """Horizontal header with an aggregate checkbox in its first section."""

    CHECKBOX_SECTION = 0

    def __init__(self, checkbox: AggregateSelectionCheckBox, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.checkbox = checkbox
        self.checkbox.setParent(self.viewport())
        self.checkbox.setText("")
        self.checkbox.setFixedSize(26, 26)
        self.checkbox.show()
        self.sectionResized.connect(lambda *_args: self._position_checkbox())
        self.geometriesChanged.connect(self._position_checkbox)

    def _position_checkbox(self):
        """Keep the control aligned as columns and DPI geometry change."""
        section_x = self.sectionViewportPosition(self.CHECKBOX_SECTION)
        section_width = self.sectionSize(self.CHECKBOX_SECTION)
        x = section_x + max(0, (section_width - self.checkbox.width()) // 2)
        y = max(0, (self.height() - self.checkbox.height()) // 2)
        self.checkbox.move(x, y)
        self.checkbox.setVisible(section_x + section_width > 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_checkbox()

    def paintEvent(self, event):
        super().paintEvent(event)
        self._position_checkbox()

    def mouseReleaseEvent(self, event):
        # Make the whole first header cell a convenient selection target while
        # the child checkbox continues to handle direct indicator clicks.
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.logicalIndexAt(event.position().toPoint()) == self.CHECKBOX_SECTION
            and self.checkbox.isEnabled()
        ):
            self.checkbox.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CheckableResultTable(QTableView):
    """Table that reports first-column presses without editing model data.

    Native item delegates can receive an incomplete press/release sequence when
    the pointer moves by a pixel, especially with display scaling. Handling the
    first-column press at the view level avoids that platform-dependent path.
    The main window applies the change through the same bulk-selection method
    used by its reliable "Check all visible" checkbox.
    """

    CHECKBOX_COLUMN = 0
    checkboxPressed = pyqtSignal(QModelIndex)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkbox_press_active = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            model = self.model()
            if (
                model is not None
                and index.isValid()
                and index.column() == self.CHECKBOX_COLUMN
                and model.flags(index) & Qt.ItemFlag.ItemIsUserCheckable
            ):
                self.checkboxPressed.emit(index)
                self._checkbox_press_active = True
                event.accept()
                return
        self._checkbox_press_active = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._checkbox_press_active and event.button() == Qt.MouseButton.LeftButton:
            # The press already performed the toggle. Consume the matching
            # release so Qt's default delegate cannot perform a second toggle.
            self._checkbox_press_active = False
            event.accept()
            return
        self._checkbox_press_active = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        model = self.model()
        if (
            event.button() == Qt.MouseButton.LeftButton
            and model is not None
            and index.isValid()
            and index.column() == self.CHECKBOX_COLUMN
            and model.flags(index) & Qt.ItemFlag.ItemIsUserCheckable
        ):
            # Qt reports the second press of two rapid clicks as a double-click
            # event rather than another mousePressEvent. Emit it as the second
            # selection request so two clicks always mean two toggles.
            self.checkboxPressed.emit(index)
            self._checkbox_press_active = True
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ScanResultModel(QAbstractTableModel):
    """Own scan records and native checkbox state without cell widgets."""

    HEADERS = ("", "File Name (Relative Path)", "Current Extension", "Detected Extension", "Status")
    checkedChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: list[dict] = []
        self.checked_paths: set[str] = set()
        self._row_by_path: dict[str, int] = {}
        self._repair_paths: set[str] = set()
        self._checked_repair_count = 0

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        record = self.records[index.row()]
        column = index.column()
        path = record.get("path", "")

        if role == Qt.ItemDataRole.CheckStateRole and column == 0:
            return Qt.CheckState.Checked if path in self.checked_paths else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                "",
                record.get("relative_path", ""),
                record.get("current_extension") or "(none)",
                record.get("detected_extension") or "(unknown)",
                record.get("status", ""),
            )[column]
        if role == Qt.ItemDataRole.ToolTipRole:
            error = record.get("error", "")
            return f"{path}\n{error}" if error else path
        if role == Qt.ItemDataRole.BackgroundRole:
            status = record.get("status", "")
            if status == "Repair required":
                return QColor("#FFF8E6")
            if status.startswith("Error"):
                return QColor("#FEF2F2")
            if status.startswith("Normal") or status == "Repaired successfully":
                return QColor("#F0FDF4")
            return QColor("#F8FAFC") if index.row() % 2 else QColor("#FFFFFF")
        if role == Qt.ItemDataRole.ForegroundRole:
            status = record.get("status", "")
            if status.startswith("Error"):
                return QColor("#B91C1C")
            if status == "Repair required":
                return QColor("#92400E")
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (0, 2, 3):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        path = self.records[index.row()].get("path", "")
        if not path:
            return False
        checked = value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked
        return self.set_paths_checked({path}, checked)

    def clear(self):
        self.beginResetModel()
        self.records.clear()
        self.checked_paths.clear()
        self._row_by_path.clear()
        self._repair_paths.clear()
        self._checked_repair_count = 0
        self.endResetModel()
        self.checkedChanged.emit(0)

    def append_records(self, records: list[dict]):
        if not records:
            return
        first = len(self.records)
        self.beginInsertRows(QModelIndex(), first, first + len(records) - 1)
        self.records.extend(records)
        for offset, record in enumerate(records):
            path = record.get("path", "")
            if path:
                self._row_by_path[path] = first + offset
                if record.get("status") == "Repair required":
                    self._repair_paths.add(path)
        self.endInsertRows()

    def repair_path_count(self) -> int:
        """Return the candidate count without walking the result list."""
        return len(self._repair_paths)

    def checked_repair_count(self) -> int:
        """Return the selected candidate count in constant time."""
        return self._checked_repair_count

    def has_checked_repairs(self) -> bool:
        return self._checked_repair_count > 0

    def checked_repair_records(self) -> list[dict]:
        return [
            record for record in self.records
            if record.get("path") in self.checked_paths
            and record.get("status") == "Repair required"
        ]

    def set_paths_checked(self, paths: set[str], checked: bool):
        """Apply one or many path selections through a single shared path.

        A one-file change only repaints that row. Bulk changes use one broad
        notification, preserving the performance of "Check all visible".
        """
        valid_paths = paths.intersection(self._row_by_path)
        changed_paths = (
            valid_paths.difference(self.checked_paths)
            if checked
            else valid_paths.intersection(self.checked_paths)
        )
        if not changed_paths:
            return False

        if checked:
            self.checked_paths.update(changed_paths)
        else:
            self.checked_paths.difference_update(changed_paths)
        changed_repair_count = len(changed_paths.intersection(self._repair_paths))
        if checked:
            self._checked_repair_count += changed_repair_count
        else:
            self._checked_repair_count -= changed_repair_count

        if len(changed_paths) == 1:
            row = self._row_by_path[next(iter(changed_paths))]
            changed_index = self.index(row, 0)
            self.dataChanged.emit(
                changed_index, changed_index, [Qt.ItemDataRole.CheckStateRole]
            )
        elif self.records:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.records) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole]
            )
        self.checkedChanged.emit(len(self.checked_paths))
        return True


class RepairFilterModel(QSortFilterProxyModel):
    """Filter repair candidates without copying or rebuilding source rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repair_only = False
        # Scan records are immutable after insertion. Disabling dynamic
        # refiltering prevents a checkbox-only dataChanged signal from making
        # Qt reconsider a very large source model.
        self.setDynamicSortFilter(False)

    def set_repair_only(self, enabled: bool):
        if self._repair_only != enabled:
            self._repair_only = enabled
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._repair_only:
            return True
        model = self.sourceModel()
        if model is None or source_row >= len(model.records):
            return False
        return model.records[source_row].get("status") == "Repair required"

    def visible_paths(self) -> set[str]:
        paths: set[str] = set()
        for row in range(self.rowCount()):
            source_index = self.mapToSource(self.index(row, 0))
            record = self.sourceModel().records[source_index.row()]
            path = record.get("path", "")
            if path:
                paths.add(path)
        return paths

    def selection_counts(self) -> tuple[int, int]:
        """Return visible/checked counts without iterating over proxy rows."""
        model = self.sourceModel()
        if not isinstance(model, ScanResultModel):
            return 0, 0
        if self._repair_only:
            return model.repair_path_count(), model.checked_repair_count()
        return len(model.records), len(model.checked_paths)
