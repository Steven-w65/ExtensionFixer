# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Streaming, cancellable directory scanning."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterator

from .detector import MagicNumberDetector


LogCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]


class FileScanner:
    """Produce file metadata without changing the file system."""

    def __init__(self, detector: MagicNumberDetector):
        self.detector = detector

    @staticmethod
    def parse_blacklist(text: str) -> set[str]:
        result: set[str] = set()
        for item in text.split(","):
            suffix = item.strip().lower()
            if suffix:
                result.add(suffix if suffix.startswith(".") else f".{suffix}")
        return result

    @staticmethod
    def format_size(size: int) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        value = float(size)
        unit_index = 0
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1
        return f"{int(value)} B" if unit_index == 0 else f"{value:.2f} {units[unit_index]}"

    def scan_iter(
        self,
        root_folder: Path | str,
        recursive: bool,
        max_size_mb: float,
        blacklist: set[str],
        logger: LogCallback,
        cancelled: CancelCallback | None = None,
    ) -> Iterator[dict]:
        root = Path(root_folder)
        max_bytes = int(max_size_mb * 1024 * 1024) if max_size_mb > 0 else 0
        iterator = (
            self._recursive_files(root, logger, cancelled)
            if recursive
            else self._top_level_files(root, logger, cancelled)
        )

        for file_path in iterator:
            if cancelled and cancelled():
                return
            record = self._scan_one(root, file_path, max_bytes, blacklist)
            yield record
            if record["status"].startswith("Error"):
                logger(f"Read error: {record['relative_path']} - {record['error']}")

    @staticmethod
    def _top_level_files(
        root: Path, logger: LogCallback, cancelled: CancelCallback | None
    ) -> Iterator[Path]:
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if cancelled and cancelled():
                        return
                    try:
                        if entry.is_file(follow_symlinks=False):
                            yield Path(entry.path)
                    except OSError as error:
                        logger(f"Skipped unreadable entry: {entry.path} - {error}")
        except OSError as error:
            logger(f"Skipped unreadable folder: {root} - {error}")

    @staticmethod
    def _recursive_files(
        root: Path, logger: LogCallback, cancelled: CancelCallback | None
    ) -> Iterator[Path]:
        stack = [root]
        while stack:
            if cancelled and cancelled():
                return
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if cancelled and cancelled():
                            return
                        try:
                            path = Path(entry.path)
                            if entry.is_dir(follow_symlinks=False):
                                if current == root and entry.name.lower() == "backup":
                                    continue
                                stack.append(path)
                            elif entry.is_file(follow_symlinks=False):
                                yield path
                        except OSError as error:
                            logger(f"Skipped unreadable entry: {entry.path} - {error}")
            except OSError as error:
                logger(f"Skipped unreadable folder: {current} - {error}")

    def _scan_one(
        self, root: Path, file_path: Path, max_bytes: int, blacklist: set[str]
    ) -> dict:
        record = {
            "path": str(file_path),
            "relative_path": str(file_path.relative_to(root)),
            "file_name": file_path.name,
            "current_extension": file_path.suffix.lower(),
            "detected_extension": "",
            "status": "",
            "size_bytes": 0,
            "size_display": "",
            "planned_path": "",
            "error": "",
        }
        if file_path.is_symlink():
            record["status"] = "Skipped: symbolic link"
            return record
        try:
            size = file_path.stat().st_size
            record["size_bytes"] = size
            record["size_display"] = self.format_size(size)
        except OSError as error:
            record["status"] = "Error: unable to read metadata"
            record["error"] = str(error)
            return record

        if record["current_extension"] in blacklist:
            record["status"] = "Skipped: blacklisted extension"
            return record
        if max_bytes and size > max_bytes:
            record["status"] = "Skipped: exceeds size limit"
            return record

        extension, error = self.detector.detect(file_path)
        if error:
            record["status"] = "Error: cannot read file"
            record["error"] = error
        elif extension is None:
            record["status"] = "Unidentifiable: no supported magic number"
        else:
            record["detected_extension"] = f".{extension}"
            record["status"] = (
                "Normal: extension matches"
                if record["current_extension"] == record["detected_extension"]
                else "Repair required"
            )
        return record
