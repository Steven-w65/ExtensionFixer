# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Overwrite-safe repair, backup, operation history, and undo services."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, Iterable

from .detector import MagicNumberDetector


Logger = Callable[[str], None]


class FileOperations:
    """Perform file-name changes without modifying original file content."""

    STRATEGIES = {
        1: "Auto append serial number",
        2: "Skip when duplicate name exists",
        3: "Safe mode: forbid overwriting",
    }

    def __init__(
        self,
        log_path: Path | str,
        detector: MagicNumberDetector | None = None,
    ):
        self.log_path = Path(log_path)
        self.detector = detector
        self.last_log_error = ""
        self._counter = 0

    @staticmethod
    def path_exists(path: Path | str) -> bool:
        return os.path.lexists(path)

    def unique_id(self) -> str:
        self._counter += 1
        return f"{time.time_ns()}_{os.getpid()}_{self._counter}"

    def load_operations(self) -> list[dict]:
        self.last_log_error = ""
        if not self.log_path.exists():
            return []
        try:
            with self.log_path.open("r", encoding="utf-8") as handle:
                content = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            self.last_log_error = f"Cannot read operation_log.json: {error}"
            return []
        if not isinstance(content, list) or not all(isinstance(item, dict) for item in content):
            self.last_log_error = "operation_log.json must contain a JSON list of objects."
            return []
        return content

    def save_operations(self, operations: list[dict]) -> tuple[bool, str]:
        temporary = self.log_path.with_name(f".{self.log_path.name}.{os.getpid()}.tmp")
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(operations, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self.log_path)
            return True, ""
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False, str(error)

    @staticmethod
    def move_without_overwrite(source: Path, target: Path) -> None:
        """Move a regular file while refusing to replace an existing path."""
        if FileOperations.path_exists(target):
            raise FileExistsError(f"Target already exists: {target}")
        if os.name == "nt":
            os.rename(source, target)
            return

        # POSIX rename can replace a target. Creating a hard link first gives
        # an atomic no-replacement check for regular files.
        os.link(source, target)
        try:
            os.unlink(source)
        except OSError:
            # Keeping both names is safer than deleting either after failure.
            raise

    @staticmethod
    def copy_file(source: Path, target: Path) -> None:
        with source.open("rb") as source_handle, target.open("xb") as target_handle:
            while True:
                block = source_handle.read(1024 * 1024)
                if not block:
                    break
                target_handle.write(block)

    def backup_file(self, source: Path, root: Path, backup_root: Path) -> tuple[bool, str]:
        try:
            relative = source.relative_to(root)
        except ValueError:
            return False, f"Source is outside the selected folder: {source}"
        target = backup_root / relative
        temporary = target.with_name(f".{target.name}.{os.getpid()}.partial")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if self.path_exists(target):
                raise FileExistsError(f"Backup target already exists: {target}")
            self.copy_file(source, temporary)
            self.move_without_overwrite(temporary, target)
            return True, ""
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False, str(error)

    def _auto_target(self, source: Path, extension: str, reserved: set[str]) -> Path:
        target = source.with_suffix(extension)
        serial = 1
        while self.path_exists(target) or os.path.normcase(str(target)) in reserved:
            target = source.parent / f"{source.stem}_{serial}{extension}"
            serial += 1
        return target

    def plan_renames(
        self, records: Iterable[dict], strategy: str
    ) -> tuple[list[tuple[dict, Path, Path]], list[str], str]:
        planned: list[tuple[dict, Path, Path]] = []
        conflicts: list[str] = []
        reserved: set[str] = set()

        for record in records:
            source = Path(record.get("path", ""))
            extension = str(record.get("detected_extension", ""))
            if not source.is_absolute() or not extension.startswith("."):
                return [], conflicts, "Repair plan contains an unsafe or malformed record."
            target = source.with_suffix(extension)
            conflict = self.path_exists(target) or os.path.normcase(str(target)) in reserved
            if conflict:
                conflicts.append(str(target))
                if strategy == self.STRATEGIES[1]:
                    target = self._auto_target(source, extension, reserved)
                elif strategy == self.STRATEGIES[2]:
                    record["planned_path"] = ""
                    continue
                else:
                    return [], conflicts, (
                        "Safe mode cancelled the operation because a target name already exists."
                    )
            reserved.add(os.path.normcase(str(target)))
            record["planned_path"] = str(target)
            planned.append((record, source, target))
        return planned, conflicts, ""

    def rename_records(
        self,
        records: list[dict],
        root_path: Path | str,
        strategy: str,
        enable_backup: bool,
        max_size_mb: float,
        logger: Logger,
        blacklist: set[str] | None = None,
    ) -> dict:
        root = Path(root_path).resolve()
        planned, conflicts, planning_error = self.plan_renames(records, strategy)
        if planning_error:
            return self._result(0, len(records), 0, planning_error, conflicts)

        operations = self.load_operations()
        if self.last_log_error:
            return self._result(
                0, 0, len(planned),
                f"Repair blocked to protect undo history: {self.last_log_error}",
                conflicts,
            )

        backup_root: Path | None = None
        if enable_backup and planned:
            backup_root = root / "backup" / self.unique_id()
            try:
                backup_root.mkdir(parents=True, exist_ok=False)
            except OSError as error:
                return self._result(
                    0, 0, len(planned), f"Could not create backup folder: {error}", conflicts
                )

        batch_id = self.unique_id()
        existing_ids = {self.operation_batch_id(item) for item in operations}
        while batch_id in existing_ids:
            batch_id = self.unique_id()

        renamed = 0
        skipped = len(records) - len(planned)
        failed = 0
        max_bytes = int(max_size_mb * 1024 * 1024) if max_size_mb > 0 else 0
        active_blacklist = blacklist or set()

        for record, source, target in planned:
            try:
                resolved_parent = source.parent.resolve()
                if not resolved_parent.is_relative_to(root):
                    raise OSError(f"Source is outside the selected folder: {source}")
                if source.is_symlink():
                    record["status"] = "Skipped: symbolic link"
                    skipped += 1
                    continue
                if source.suffix.lower() in active_blacklist:
                    record["status"] = "Skipped: blacklisted extension"
                    skipped += 1
                    logger(f"Skipped blacklisted file: {source}")
                    continue
                size = source.stat().st_size
                if max_bytes and size > max_bytes:
                    record["status"] = "Skipped: exceeds current size limit"
                    skipped += 1
                    continue
                if self.detector is not None:
                    detected, detection_error = self.detector.detect(source)
                    expected = str(record.get("detected_extension", "")).lstrip(".")
                    if detection_error:
                        raise OSError(f"Could not recheck file format: {detection_error}")
                    if detected != expected:
                        record["status"] = "Skipped: detected format changed after scan"
                        skipped += 1
                        logger(f"Skipped changed file: {source}")
                        continue
                if self.path_exists(target):
                    record["status"] = "Skipped: target name now exists"
                    skipped += 1
                    continue

                if backup_root is not None:
                    backup_ok, backup_error = self.backup_file(source, root, backup_root)
                    if not backup_ok:
                        record["status"] = "Error: backup failed"
                        record["error"] = backup_error
                        failed += 1
                        logger(f"Backup failed: {source} - {backup_error}")
                        continue

                operation = {
                    "source": str(source),
                    "destination": str(target),
                    "backup": str(backup_root) if backup_root else "",
                    "root_folder": str(root),
                    "batch_id": batch_id,
                    "state": "prepared",
                    "size_bytes": size,
                }
                operations.append(operation)
                saved, error = self.save_operations(operations)
                if not saved:
                    operations.pop()
                    raise OSError(f"Could not save undo record: {error}")

                self.move_without_overwrite(source, target)
                operation["state"] = "completed"
                saved, error = self.save_operations(operations)
                if not saved:
                    logger(f"Warning: rename completed but undo state update failed - {error}")

                record.update({
                    "path": str(target),
                    "relative_path": str(target.relative_to(root)),
                    "file_name": target.name,
                    "current_extension": target.suffix.lower(),
                    "status": "Repaired successfully",
                })
                renamed += 1
                logger(f"Renamed: {source.name} -> {target.name}")
            except OSError as error:
                record["status"] = "Error: rename failed"
                record["error"] = str(error)
                failed += 1
                logger(f"Rename failed: {source} - {error}")

        return self._result(renamed, skipped, failed, "", conflicts)

    @staticmethod
    def _result(
        renamed: int, skipped: int, failed: int, message: str, conflicts: list[str]
    ) -> dict:
        return {
            "renamed": renamed,
            "skipped": skipped,
            "failed": failed,
            "message": message,
            "conflicts": conflicts,
        }

    @staticmethod
    def operation_batch_id(operation: dict) -> str:
        return str(operation.get("batch_id") or "legacy")

    def get_latest_batch(self) -> tuple[str, list[dict]]:
        operations = self.load_operations()
        if self.last_log_error or not operations:
            return "", []
        batch_id = self.operation_batch_id(operations[-1])
        return batch_id, [
            item for item in operations if self.operation_batch_id(item) == batch_id
        ]

    def inspect_undo_operation(self, operation: dict) -> tuple[str, str]:
        original = Path(str(operation.get("source", "")))
        renamed = Path(str(operation.get("destination", "")))
        root_text = str(operation.get("root_folder", "")).strip()
        root = Path(root_text) if root_text else None
        if (
            not original.is_absolute()
            or not renamed.is_absolute()
            or original.parent != renamed.parent
            or original == renamed
        ):
            return "Blocked", "Unsafe or malformed operation-log entry"
        if root is None or not root.is_absolute():
            return "Blocked", "Missing or invalid recorded scan folder"
        if not original.is_relative_to(root) or not renamed.is_relative_to(root):
            return "Blocked", "Path is outside the recorded scan folder"
        try:
            resolved_root = root.resolve()
            resolved_original_parent = original.parent.resolve()
            resolved_renamed_parent = renamed.parent.resolve()
        except (OSError, RuntimeError) as error:
            return "Blocked", f"Cannot validate recorded paths: {error}"
        if (
            not resolved_original_parent.is_relative_to(resolved_root)
            or not resolved_renamed_parent.is_relative_to(resolved_root)
        ):
            return "Blocked", "Resolved path is outside the recorded scan folder"
        if original.is_symlink() or renamed.is_symlink():
            return "Blocked", "Symbolic links cannot be restored"

        source_exists = self.path_exists(original)
        destination_exists = self.path_exists(renamed)
        if source_exists and not destination_exists:
            return "Stale", "Rename did not complete; log entry can be cleared"
        if not destination_exists:
            return "Blocked", "Renamed file is missing"
        if source_exists:
            return "Blocked", "Original filename already exists"

        recorded_size = operation.get("size_bytes")
        if isinstance(recorded_size, int):
            try:
                if renamed.stat().st_size != recorded_size:
                    return "Blocked", "Renamed file size changed after repair"
            except OSError as error:
                return "Blocked", f"Cannot inspect renamed file: {error}"
        return "Ready", "Ready to restore original filename"

    def _preview(self, operations: list[dict], include_batch: bool) -> list[dict]:
        preview: list[dict] = []
        for operation in reversed(operations):
            status, detail = self.inspect_undo_operation(operation)
            item = {
                "operation": operation,
                "current_name": Path(str(operation.get("destination", ""))).name,
                "original_name": Path(str(operation.get("source", ""))).name,
                "status": status,
                "detail": detail,
            }
            if include_batch:
                item["batch_id"] = self.operation_batch_id(operation)
            preview.append(item)
        return preview

    def preview_latest_batch(self) -> tuple[str, list[dict], str]:
        batch_id, operations = self.get_latest_batch()
        if self.last_log_error:
            return "", [], self.last_log_error
        if not operations:
            return "", [], "No recorded rename operations are available to undo."
        return batch_id, self._preview(operations, False), ""

    def preview_all_operations(self) -> tuple[list[dict], str]:
        operations = self.load_operations()
        if self.last_log_error:
            return [], self.last_log_error
        if not operations:
            return [], "No recorded rename operations are available to undo."
        return self._preview(operations, True), ""

    def undo_batch(self, batch_id: str | None, logger: Logger) -> tuple[int, int, str]:
        operations = self.load_operations()
        if self.last_log_error:
            return 0, 0, self.last_log_error
        selected = operations if batch_id is None else [
            item for item in operations if self.operation_batch_id(item) == batch_id
        ]
        if not selected:
            return 0, 0, "The selected undo batch is no longer available."

        undone = 0
        failed = 0
        completed_ids: set[int] = set()
        for operation in reversed(selected):
            status, detail = self.inspect_undo_operation(operation)
            original = Path(str(operation.get("source", "")))
            renamed = Path(str(operation.get("destination", "")))
            if status == "Stale":
                completed_ids.add(id(operation))
                logger(f"Undo cleared stale entry: {original}")
                continue
            if status != "Ready":
                failed += 1
                logger(f"Undo skipped: {renamed} - {detail}")
                continue
            try:
                self.move_without_overwrite(renamed, original)
                completed_ids.add(id(operation))
                undone += 1
                logger(f"Undo: {renamed.name} -> {original.name}")
            except OSError as error:
                failed += 1
                logger(f"Undo failed: {renamed} - {error}")

        remaining = [item for item in operations if id(item) not in completed_ids]
        saved, error = self.save_operations(remaining)
        if not saved:
            return undone, failed, f"Undo completed, but the operation log could not be updated: {error}"
        return undone, failed, ""
