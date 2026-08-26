# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""CSV reporting kept independent from the GUI and worker implementation."""

from __future__ import annotations

import csv
from pathlib import Path


REPORT_FIELDS = (
    "relative_path",
    "full_path",
    "file_name",
    "current_extension",
    "detected_real_extension",
    "size_bytes",
    "size_display",
    "status",
    "planned_target",
    "error",
)


def export_csv_report(records: list[dict], destination: Path | str) -> str:
    """Export a stable metadata schema and return the absolute report path."""
    path = Path(destination).resolve()
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({
                "relative_path": record.get("relative_path", ""),
                "full_path": record.get("path", ""),
                "file_name": record.get("file_name", ""),
                "current_extension": record.get("current_extension", ""),
                "detected_real_extension": record.get("detected_extension", ""),
                "size_bytes": record.get("size_bytes", 0),
                "size_display": record.get("size_display", ""),
                "status": record.get("status", ""),
                "planned_target": record.get("planned_path", ""),
                "error": record.get("error", ""),
            })
    return str(path)
