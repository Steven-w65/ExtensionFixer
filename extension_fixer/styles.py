# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Modern, restrained, and DPI-friendly application styling."""

APP_STYLE = """
QWidget {
    color: #172033;
    font-family: "Segoe UI Variable", "Segoe UI";
    font-size: 10.25pt;
}
QMainWindow, QDialog, QWidget#appSurface { background: #F5F7FB; }
QLabel { color: #334155; background: transparent; }
QLabel#appTitle { color: #0F172A; font-size: 20pt; font-weight: 700; }
QLabel#appSubtitle { color: #64748B; font-size: 9.5pt; }
QLabel#versionBadge {
    color: #475569;
    background: #E9EEF6;
    border: 1px solid #D7DFEA;
    border-radius: 10px;
    padding: 4px 10px;
    font-size: 8.5pt;
    font-weight: 600;
}
QLabel#sectionCaption {
    color: #64748B;
    font-size: 8pt;
    font-weight: 700;
}
QLabel#sectionTitle { color: #172033; font-size: 10.5pt; font-weight: 700; }
QLabel#metricsLabel {
    color: #475569;
    background: #F1F5F9;
    border-radius: 8px;
    padding: 5px 9px;
    font-size: 9pt;
}
QLabel#activityHint { color: #8492A6; font-size: 8.75pt; }
QLabel#dialogHint { color: #64748B; font-size: 9.5pt; }

QFrame#card, QFrame#resultsCard, QFrame#activityCard {
    background: #FFFFFF;
    border: 1px solid #DDE4ED;
    border-radius: 12px;
}
QWidget#resultsToolbar, QWidget#activityHeader {
    background: #FFFFFF;
    border: 0;
    border-bottom: 1px solid #E7ECF2;
}

QTabWidget::pane {
    background: #FFFFFF;
    border: 1px solid #DDE4ED;
    border-radius: 10px;
    top: -1px;
}
QTabWidget QWidget { background: #FFFFFF; }
QTabBar::tab {
    min-height: 24px;
    color: #64748B;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    padding: 9px 18px;
    font-weight: 600;
}
QTabBar::tab:selected { color: #1D4ED8; border-bottom-color: #2563EB; }
QTabBar::tab:hover:!selected { color: #334155; background: #F1F5F9; }
QTabBar::tab:focus { border: 1px solid #93C5FD; border-radius: 6px; }

QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit,
QTableView, QTableWidget {
    color: #172033;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 7px 9px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}
QLineEdit, QComboBox, QDoubleSpinBox { min-height: 24px; }
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover,
QTextEdit:hover, QPlainTextEdit:hover { border-color: #94A3B8; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus, QTableView:focus, QTableWidget:focus {
    border: 2px solid #60A5FA;
}
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {
    color: #64748B;
    background: #EEF2F7;
    border-color: #D7DFE8;
}
QComboBox::drop-down { width: 28px; border: 0; }
QComboBox QAbstractItemView {
    color: #172033;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 4px;
}

QCheckBox { color: #334155; spacing: 8px; min-height: 28px; }
QCheckBox:disabled { color: #94A3B8; }
QCheckBox:focus { color: #1D4ED8; }

QPushButton {
    min-height: 24px;
    min-width: 82px;
    color: #334155;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 7px 15px;
    font-weight: 600;
}
QPushButton:hover { color: #1E3A5F; background: #F1F5F9; border-color: #94A3B8; }
QPushButton:pressed { background: #E2E8F0; border-color: #64748B; }
QPushButton:focus { border: 2px solid #60A5FA; padding: 6px 14px; }
QPushButton:disabled {
    color: #7C899B;
    background: #E9EEF4;
    border-color: #D5DDE7;
}
QPushButton#quietButton { background: #F8FAFC; }
QPushButton#quietButton:hover { background: #EEF3F8; }

QPushButton#primaryButton {
    color: #FFFFFF;
    background: #2563EB;
    border-color: #2563EB;
    font-weight: 700;
}
QPushButton#primaryButton:hover { background: #1D4ED8; border-color: #1D4ED8; }
QPushButton#primaryButton:pressed { background: #1E40AF; border-color: #1E40AF; }
QPushButton#primaryButton:focus { border: 2px solid #93C5FD; }
QPushButton#primaryButton:disabled {
    color: #738196;
    background: #DDE5EF;
    border-color: #D1DAE6;
}

QPushButton#dangerButton {
    color: #FFFFFF;
    background: #DC2626;
    border-color: #DC2626;
    font-weight: 700;
}
QPushButton#dangerButton:hover { background: #B91C1C; border-color: #B91C1C; }
QPushButton#dangerButton:pressed { background: #991B1B; border-color: #991B1B; }
QPushButton#dangerButton:focus { border: 2px solid #FCA5A5; }
QPushButton#dangerButton:disabled {
    color: #738196;
    background: #DDE5EF;
    border-color: #D1DAE6;
}

QTableView#resultsTable {
    background: #FFFFFF;
    border: 0;
    border-radius: 0;
    padding: 0;
    gridline-color: #E8EDF3;
}
QPlainTextEdit#activityLog {
    background: #FBFCFE;
    border: 0;
    border-radius: 0;
    padding: 10px 14px;
    color: #475569;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 9.25pt;
}
QHeaderView::section {
    min-height: 29px;
    color: #475569;
    background: #F8FAFC;
    border: 0;
    border-right: 1px solid #E5EAF0;
    border-bottom: 1px solid #DDE4ED;
    padding: 8px;
    font-size: 9pt;
    font-weight: 700;
}
QTableCornerButton::section {
    background: #F8FAFC;
    border: 0;
    border-right: 1px solid #E5EAF0;
    border-bottom: 1px solid #DDE4ED;
}

QProgressBar {
    min-height: 8px;
    max-height: 8px;
    background: #E7EDF4;
    border: 0;
    border-radius: 4px;
}
QProgressBar::chunk { background: #3B82F6; border-radius: 4px; }

QStatusBar {
    color: #64748B;
    background: #F1F5F9;
    border-top: 1px solid #E2E8F0;
    font-size: 9pt;
}
QStatusBar QLabel { color: #64748B; }

QScrollBar:vertical { width: 13px; background: #F1F5F9; border: 0; margin: 0; }
QScrollBar::handle:vertical {
    min-height: 34px;
    background: #AAB7C7;
    border-radius: 6px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover { background: #8495A9; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 13px; background: #F1F5F9; border: 0; }
QScrollBar::handle:horizontal {
    min-width: 34px;
    background: #AAB7C7;
    border-radius: 6px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover { background: #8495A9; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QSplitter::handle { background: #E4E9F0; }
QSplitter::handle:vertical { height: 7px; }
QToolTip {
    color: #FFFFFF;
    background: #1E293B;
    border: 1px solid #0F172A;
    border-radius: 5px;
    padding: 6px;
}
"""
