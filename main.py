import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from pathlib import Path
import json
import csv
import sys
import queue
import threading
import uuid
import ctypes

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ApplicationSettings:
    """Loads and saves all non-format application preferences."""

    DEFAULTS = {
        "last_folder": "",
        "recursive_scan": True,
        "show_only_repair_items": False,
        "enable_backup": True,
        "duplicate_strategy": 1,
        "max_size_mb": "1024",
        "suffix_blacklist": ".exe, .dll",
    }

    def __init__(self, settings_path):
        self.settings_path = Path(settings_path)

    def load(self):
        settings = dict(self.DEFAULTS)

        if not self.settings_path.exists():
            return settings

        try:
            with open(self.settings_path, "r", encoding="utf-8") as file_handle:
                stored_settings = json.load(file_handle)

            if isinstance(stored_settings, dict):
                for key in settings:
                    if key in stored_settings:
                        settings[key] = stored_settings[key]
        except (OSError, json.JSONDecodeError):
            pass

        # Migrate older text-based settings to the compact numeric form.
        strategy = settings["duplicate_strategy"]
        if isinstance(strategy, str):
            strategy_map = {
                "Auto append serial number": 1,
                "Skip when duplicate name exists": 2,
                "Safe mode: forbid overwriting": 3,
            }
            settings["duplicate_strategy"] = strategy_map.get(strategy, 1)

        if settings["duplicate_strategy"] not in (1, 2, 3):
            settings["duplicate_strategy"] = 1

        for setting_name in (
            "recursive_scan",
            "show_only_repair_items",
            "enable_backup",
        ):
            value = settings[setting_name]
            if isinstance(value, str):
                settings[setting_name] = value.strip().lower() in ("1", "true", "yes", "on")
            else:
                settings[setting_name] = bool(value)

        try:
            size_limit = float(settings["max_size_mb"])
            if not (0 <= size_limit <= 1000000):
                raise ValueError
        except (TypeError, ValueError):
            settings["max_size_mb"] = self.DEFAULTS["max_size_mb"]

        return settings

    def save(self, settings):
        temporary_path = self.settings_path.with_name(
            f".{self.settings_path.name}.{os.getpid()}.tmp"
        )
        try:
            with open(temporary_path, "w", encoding="utf-8") as file_handle:
                json.dump(settings, file_handle, ensure_ascii=False, indent=2)
            os.replace(temporary_path, self.settings_path)
            return True, ""
        except OSError as error:
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except OSError:
                pass
            return False, str(error)


class MagicNumberDetector:
    """Detects formats using signatures defined entirely in a JSON file."""

    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.custom_formats = []

    @staticmethod
    def _atomic_json_write(path, content):
        """Write JSON through a temporary file so a crash cannot truncate it."""
        path = Path(path)
        temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")

        try:
            with open(temporary_path, "w", encoding="utf-8") as file_handle:
                json.dump(content, file_handle, ensure_ascii=False, indent=2)
            os.replace(temporary_path, path)
            return True, ""
        except OSError as error:
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except OSError:
                pass
            return False, str(error)

    @staticmethod
    def _parse_formats(configuration):
        """Validate configuration without changing the currently active rules."""
        formats = configuration.get("formats", []) if isinstance(configuration, dict) else []
        parsed_formats = []
        errors = []

        if not isinstance(formats, list):
            return [], ["Format configuration field 'formats' must be a list."]

        for index, item in enumerate(formats, start=1):
            try:
                if not isinstance(item, dict):
                    raise ValueError("must be an object")

                extension = str(item.get("extension", "")).strip().lower().lstrip(".")
                if not extension or any(character in extension for character in '\\\\/:*?\"<>|'):
                    raise ValueError("contains an invalid extension")

                raw_signatures = item.get("signatures")
                if raw_signatures is None:
                    raw_signatures = [{
                        "offset": item.get("offset", 0),
                        "signature_hex": item.get("signature_hex", ""),
                    }]

                if not isinstance(raw_signatures, list) or not raw_signatures:
                    raise ValueError("requires a non-empty signatures list")

                signature_parts = []
                for signature_item in raw_signatures:
                    if not isinstance(signature_item, dict):
                        raise ValueError("each signature must be an object")

                    offset = signature_item.get("offset", 0)
                    signature_hex = str(
                        signature_item.get("signature_hex", "")
                    ).replace(" ", "")

                    if not isinstance(offset, int) or offset < 0 or offset > 15:
                        raise ValueError("offset must be an integer from 0 through 15")

                    signature = bytes.fromhex(signature_hex)
                    if not signature:
                        raise ValueError("signature_hex cannot be empty")
                    if offset + len(signature) > 16:
                        raise ValueError("signature extends beyond the first 16 bytes")

                    signature_parts.append((offset, signature))

                parsed_formats.append((extension, signature_parts))
            except (TypeError, ValueError) as error:
                errors.append(f"Format entry {index}: {error}")

        return parsed_formats, errors

    def load_custom_formats(self):
        """
        Load user-defined signatures from JSON.

        Each item must have an extension, an offset from 0 to 15, and a
        hexadecimal signature whose final byte remains within the 16-byte
        scan window. Invalid entries are ignored and returned as messages.
        """
        if not self.config_path.exists():
            self.custom_formats = []
            return [], []

        try:
            with open(self.config_path, "r", encoding="utf-8") as file_handle:
                configuration = json.load(file_handle)
        except (OSError, json.JSONDecodeError) as error:
            return [], [f"Cannot load format configuration: {error}"]

        parsed_formats, errors = self._parse_formats(configuration)
        if errors:
            return list(self.custom_formats), errors

        self.custom_formats = parsed_formats
        return list(self.custom_formats), []

    def save_custom_config(self, configuration_text):
        """Validate and save JSON, then make it active immediately."""
        try:
            configuration = json.loads(configuration_text)
        except json.JSONDecodeError as error:
            return False, f"Invalid JSON: {error}"

        if not isinstance(configuration, dict) or "formats" not in configuration:
            return False, "Configuration must be an object containing a 'formats' list."

        loaded_formats, errors = self._parse_formats(configuration)
        if errors:
            return False, "Configuration was not accepted:\n" + "\n".join(errors)

        success, error = self._atomic_json_write(self.config_path, configuration)
        if not success:
            return False, f"Could not save configuration: {error}"

        self.custom_formats = loaded_formats

        return True, f"Loaded {len(loaded_formats)} custom format(s)."

    def detect(self, file_path):
        """
        Read exactly up to the first 16 bytes of a file.

        Returns:
            (extension, error_message)
            extension is None when the format cannot be identified.
        """
        try:
            with open(file_path, "rb") as file_handle:
                header = file_handle.read(16)

            # The configuration is the single source of truth for all
            # signatures. Its order controls which matching rule wins.
            for extension, signature_parts in self.custom_formats:
                if all(
                    header[offset:offset + len(signature)] == signature
                    for offset, signature in signature_parts
                ):
                    return extension, ""

            return None, ""
        except OSError as error:
            return None, str(error)


class FileScanner:
    """Scans folders and produces metadata records without changing files."""

    def __init__(self, detector):
        self.detector = detector

    @staticmethod
    def parse_blacklist(blacklist_text):
        """Convert a comma-separated suffix list to normalized extensions."""
        blacklist = set()

        for item in blacklist_text.split(","):
            suffix = item.strip().lower()
            if not suffix:
                continue

            if not suffix.startswith("."):
                suffix = "." + suffix

            blacklist.add(suffix)

        return blacklist

    @staticmethod
    def format_size(file_size):
        """Return a human-readable file size without third-party modules."""
        units = ("B", "KB", "MB", "GB", "TB")
        value = float(file_size)
        unit_index = 0

        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1

        if unit_index == 0:
            return f"{int(value)} {units[unit_index]}"

        return f"{value:.2f} {units[unit_index]}"

    def scan(self, root_folder, recursive, max_size_mb, blacklist, logger):
        """Return all scan records; the GUI uses scan_iter for responsiveness."""
        return list(self.scan_iter(root_folder, recursive, max_size_mb, blacklist, logger))

    def scan_iter(self, root_folder, recursive, max_size_mb, blacklist, logger):
        """Yield scan records one at a time without loading the full result set."""
        root_path = Path(root_folder)
        max_size_bytes = int(max_size_mb * 1024 * 1024) if max_size_mb > 0 else 0

        if recursive:
            file_iterator = self._recursive_files(root_path, logger)
        else:
            file_iterator = self._top_level_files(root_path, logger)

        for file_path in file_iterator:
            record = self._scan_one_file(
                root_path,
                file_path,
                max_size_bytes,
                blacklist
            )
            yield record

            if record["status"].startswith("Error"):
                logger(f"Read error: {record['relative_path']} - {record['error']}")


    @staticmethod
    def _top_level_files(root_path, logger):
        """Stream top-level files through os.scandir for low directory overhead."""
        try:
            with os.scandir(root_path) as entries:
                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            yield Path(entry.path)
                    except OSError as error:
                        logger(f"Skipped unreadable entry: {entry.path} - {error}")
        except OSError as error:
            logger(f"Skipped unreadable folder: {root_path} - {error}")

    @staticmethod
    def _recursive_files(root_path, logger):
        """
        Stream a depth-first directory walk with os.scandir. Unlike os.walk,
        this does not build a full list of names for very large directories.
        """
        directory_stack = [Path(root_path)]

        while directory_stack:
            current_path = directory_stack.pop()
            try:
                with os.scandir(current_path) as entries:
                    for entry in entries:
                        try:
                            entry_path = Path(entry.path)
                            if entry.is_dir(follow_symlinks=False):
                                if current_path == root_path and entry.name == "backup":
                                    continue
                                directory_stack.append(entry_path)
                            elif entry.is_file(follow_symlinks=False):
                                yield entry_path
                        except OSError as error:
                            logger(f"Skipped unreadable entry: {entry.path} - {error}")
            except OSError as error:
                logger(f"Skipped unreadable folder: {current_path} - {error}")

    def _scan_one_file(self, root_path, file_path, max_size_bytes, blacklist):
        record = {
            "path": str(file_path),
            "relative_path": str(file_path.relative_to(root_path)),
            "file_name": file_path.name,
            "current_extension": file_path.suffix.lower(),
            "detected_extension": "",
            "status": "",
            "size_bytes": 0,
            "size_display": "",
            "planned_path": "",
            "error": "",
        }

        # Renaming a symbolic link can have platform-dependent behavior and
        # can point outside the selected folder, so it is never processed.
        if file_path.is_symlink():
            record["status"] = "Skipped: symbolic link"
            return record

        try:
            file_size = file_path.stat().st_size
            record["size_bytes"] = file_size
            record["size_display"] = self.format_size(file_size)
        except OSError as error:
            record["status"] = "Error: unable to read metadata"
            record["error"] = str(error)
            return record

        if record["current_extension"] in blacklist:
            record["status"] = "Skipped: blacklisted extension"
            return record

        if max_size_bytes > 0 and record["size_bytes"] > max_size_bytes:
            record["status"] = "Skipped: exceeds size limit"
            return record

        detected_extension, error = self.detector.detect(file_path)

        if error:
            record["status"] = "Error: cannot read file"
            record["error"] = error
            return record

        if not detected_extension:
            record["status"] = "Unidentifiable: no supported magic number"
            return record

        record["detected_extension"] = "." + detected_extension

        if record["current_extension"] == record["detected_extension"]:
            record["status"] = "Normal: extension matches"
            return record

        record["status"] = "Repair required"
        return record


class ScanWorker:
    """Runs FileScanner work off the Tkinter thread and emits queue events."""

    def __init__(
        self,
        scanner,
        event_queue,
        stop_event,
        scan_token,
        root_folder,
        recursive,
        max_size_mb,
        blacklist,
    ):
        self.scanner = scanner
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.scan_token = scan_token
        self.root_folder = root_folder
        self.recursive = recursive
        self.max_size_mb = max_size_mb
        self.blacklist = blacklist

    def emit(self, event_type, payload):
        """Put an event with backpressure while allowing prompt cancellation."""
        while True:
            try:
                self.event_queue.put((event_type, self.scan_token, payload), timeout=0.1)
                return True
            except queue.Full:
                if self.stop_event.is_set():
                    return False

    def run(self):
        """Scan files and report records, progress, errors, and completion."""
        processed_count = 0
        repair_count = 0

        try:
            def worker_log(message):
                self.emit("log", message)

            for record in self.scanner.scan_iter(
                root_folder=self.root_folder,
                recursive=self.recursive,
                max_size_mb=self.max_size_mb,
                blacklist=self.blacklist,
                logger=worker_log,
            ):
                if self.stop_event.is_set():
                    self.emit("stopped", {
                        "processed": processed_count,
                        "repair_count": repair_count,
                    })
                    return

                if not self.emit("record", record):
                    return

                processed_count += 1
                if record.get("status") == "Repair required":
                    repair_count += 1

                if processed_count % 250 == 0:
                    if not self.emit("progress", {
                        "processed": processed_count,
                        "repair_count": repair_count,
                    }):
                        return

            if self.stop_event.is_set():
                self.emit("stopped", {
                    "processed": processed_count,
                    "repair_count": repair_count,
                })
            else:
                self.emit("completed", {
                    "processed": processed_count,
                    "repair_count": repair_count,
                })
        except Exception as error:
            self.emit("error", str(error))


class FileOperations:
    """Performs safe rename, optional backup, operation logging, and undo."""

    def __init__(self, log_path):
        self.log_path = Path(log_path)
        self.last_log_error = ""
        self.batch_counter = 0

    def load_operations(self):
        """Load outstanding rename operations and retain a visible error state."""
        self.last_log_error = ""
        if not self.log_path.exists():
            return []

        try:
            with open(self.log_path, "r", encoding="utf-8") as file_handle:
                content = json.load(file_handle)

            if not isinstance(content, list):
                self.last_log_error = "operation_log.json must contain a JSON list."
                return []

            return content
        except (OSError, json.JSONDecodeError) as error:
            self.last_log_error = f"Cannot read operation_log.json: {error}"
            return []

    def save_operations(self, operations):
        """Persist undo information atomically."""
        temporary_path = self.log_path.with_name(f".{self.log_path.name}.{os.getpid()}.tmp")
        try:
            with open(temporary_path, "w", encoding="utf-8") as file_handle:
                json.dump(operations, file_handle, ensure_ascii=False, indent=2)
            os.replace(temporary_path, self.log_path)
            return True, ""
        except OSError as error:
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except OSError:
                pass
            return False, str(error)

    def create_timestamp_name(self):
        """
        Build a timestamp-like, collision-resistant folder name using only os.

        st_mtime_ns is a high-resolution timestamp supplied by the operating
        system and avoids importing non-listed modules.
        """
        try:
            timestamp = str(os.stat(".").st_mtime_ns)
        except OSError:
            timestamp = "0"

        self.batch_counter += 1
        return f"{timestamp}_{os.getpid()}_{self.batch_counter}"

    @staticmethod
    def copy_file(source_path, destination_path):
        """
        Copy binary content only for backups. Magic-number detection itself
        always reads only the first 16 bytes.
        """
        buffer_size = 1024 * 1024

        with open(source_path, "rb") as source_handle:
            with open(destination_path, "wb") as destination_handle:
                while True:
                    chunk = source_handle.read(buffer_size)
                    if not chunk:
                        break
                    destination_handle.write(chunk)

    @staticmethod
    def path_exists_including_broken_link(path):
        """Detect ordinary files as well as broken symbolic links."""
        return os.path.lexists(path)

    def move_without_overwrite(self, source_path, target_path):
        """Move without replacement on both Windows and POSIX file systems."""
        if self.path_exists_including_broken_link(target_path):
            raise FileExistsError(f"Target already exists: {target_path}")

        # Windows rename fails when the target exists, so this works on FAT,
        # exFAT, NTFS, network shares, and locations that disallow hard links.
        if os.name == "nt":
            os.rename(source_path, target_path)
            return

        # On POSIX, os.rename may overwrite an existing target. Linking first
        # makes target creation fail atomically when another process wins.
        os.link(source_path, target_path)
        try:
            os.unlink(source_path)
        except OSError:
            # Both names remain available if unlink fails; that is safer than
            # removing either file automatically.
            raise

    def backup_file(self, source_path, root_path, backup_root):
        """
        Backup original file before renaming.

        A complete independent copy is written to a temporary file first, then
        committed through a hard link. This avoids partial backup files and
        prevents an existing backup from being overwritten.
        """
        source = Path(source_path)
        root = Path(root_path)
        backup_base = Path(backup_root)

        relative_path = source.relative_to(root)
        backup_path = backup_base / relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        if self.path_exists_including_broken_link(backup_path):
            return False, f"Backup target already exists: {backup_path}"

        temporary_backup = backup_path.with_name(
            f".{backup_path.name}.{os.getpid()}.partial"
        )
        try:
            self.copy_file(source, temporary_backup)
            self.move_without_overwrite(temporary_backup, backup_path)
            return True, ""
        except OSError as error:
            try:
                if temporary_backup.exists():
                    temporary_backup.unlink()
            except OSError:
                pass
            return False, str(error)

    def build_auto_name(self, source_path, new_extension, reserved_paths):
        """Generate a non-conflicting target name by appending serial numbers."""
        source = Path(source_path)
        base_name = source.stem
        parent = source.parent
        candidate = parent / f"{base_name}{new_extension}"
        serial = 1

        while self.path_exists_including_broken_link(candidate) or str(candidate).lower() in reserved_paths:
            candidate = parent / f"{base_name}_{serial}{new_extension}"
            serial += 1

        return candidate

    def plan_renames(self, records, strategy):
        """
        Determine target names before any rename begins.

        Safe mode aborts the entire operation when any conflict exists.
        Skip mode skips only the conflicting item.
        Auto mode picks a serial-number variant.
        """
        planned = []
        reserved_paths = set()
        conflicts = []

        for record in records:
            source = Path(record["path"])
            new_extension = record["detected_extension"]
            preferred_target = source.with_suffix(new_extension)
            target = preferred_target

            has_conflict = (
                self.path_exists_including_broken_link(target) or
                str(target).lower() in reserved_paths
            )

            if has_conflict:
                conflicts.append(str(preferred_target))

                if strategy == "Auto append serial number":
                    target = self.build_auto_name(
                        source,
                        new_extension,
                        reserved_paths
                    )
                elif strategy == "Skip when duplicate name exists":
                    continue
                else:
                    return [], conflicts, (
                        "Safe mode cancelled the operation because a target "
                        "name already exists."
                    )

            reserved_paths.add(str(target).lower())
            record["planned_path"] = str(target)
            planned.append((record, source, target))

        return planned, conflicts, ""

    def rename_records(
        self,
        records,
        root_path,
        strategy,
        enable_backup,
        max_size_mb,
        logger
    ):
        """Execute planned renames and return result counters."""
        planned, conflicts, planning_error = self.plan_renames(records, strategy)

        if planning_error:
            return {
                "renamed": 0,
                "skipped": len(records),
                "failed": 0,
                "message": planning_error,
                "conflicts": conflicts,
            }

        backup_root = None
        if enable_backup and planned:
            timestamp_name = self.create_timestamp_name()
            backup_root = Path(root_path) / "backup" / timestamp_name

            try:
                backup_root.mkdir(parents=True, exist_ok=False)
            except OSError as error:
                return {
                    "renamed": 0,
                    "skipped": 0,
                    "failed": len(planned),
                    "message": f"Could not create backup folder: {error}",
                    "conflicts": conflicts,
                }

        operation_log = self.load_operations()
        if self.last_log_error:
            return {
                "renamed": 0,
                "skipped": 0,
                "failed": len(planned),
                "message": (
                    f"Repair blocked to protect undo history: {self.last_log_error}"
                ),
                "conflicts": conflicts,
            }
        batch_id = self.create_timestamp_name()
        existing_batch_ids = {
            self.operation_batch_id(operation) for operation in operation_log
        }
        while batch_id in existing_batch_ids:
            batch_id = self.create_timestamp_name()
        renamed_count = 0
        skipped_count = len(records) - len(planned)
        failed_count = 0
        max_size_bytes = int(max_size_mb * 1024 * 1024) if max_size_mb > 0 else 0

        for record, source, target in planned:
            try:
                if source.is_symlink():
                    record["status"] = "Skipped: symbolic link"
                    skipped_count += 1
                    continue

                if max_size_bytes > 0 and source.stat().st_size > max_size_bytes:
                    record["status"] = "Skipped: exceeds current size limit"
                    skipped_count += 1
                    continue

                # Check once again directly before renaming to prevent overwrite.
                if self.path_exists_including_broken_link(target):
                    record["status"] = "Skipped: target name now exists"
                    skipped_count += 1
                    continue

                if enable_backup:
                    backup_ok, backup_error = self.backup_file(
                        source,
                        root_path,
                        backup_root
                    )
                    if not backup_ok:
                        record["status"] = "Error: backup failed"
                        record["error"] = backup_error
                        failed_count += 1
                        logger(f"Backup failed: {source} - {backup_error}")
                        continue

                operation = {
                    "source": str(source),
                    "destination": str(target),
                    "backup": str(backup_root) if backup_root else "",
                    "root_folder": str(root_path),
                    "batch_id": batch_id,
                    "state": "prepared",
                }
                operation_log.append(operation)

                # Save before the name change. If the application stops after
                # the move, Undo can safely inspect this prepared operation.
                save_ok, save_error = self.save_operations(operation_log)
                if not save_ok:
                    operation_log.pop()
                    raise OSError(f"Could not save undo record: {save_error}")

                self.move_without_overwrite(source, target)
                operation["state"] = "completed"

                save_ok, save_error = self.save_operations(operation_log)
                if not save_ok:
                    logger(f"Warning: rename completed but undo state update failed - {save_error}")

                record["path"] = str(target)
                record["relative_path"] = str(target.relative_to(Path(root_path)))
                record["file_name"] = target.name
                record["current_extension"] = target.suffix.lower()
                record["status"] = "Repaired successfully"
                renamed_count += 1
                logger(f"Renamed: {source.name} -> {target.name}")

            except OSError as error:
                record["status"] = "Error: rename failed"
                record["error"] = str(error)
                failed_count += 1
                logger(f"Rename failed: {source} - {error}")

        return {
            "renamed": renamed_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "message": "",
            "conflicts": conflicts,
        }

    @staticmethod
    def operation_batch_id(operation):
        """Old logs without a batch ID are treated as one legacy batch."""
        return str(operation.get("batch_id") or "legacy")

    def get_latest_batch(self):
        """Return the most recently recorded pending batch and its entries."""
        operations = self.load_operations()
        if self.last_log_error or not operations:
            return "", []

        batch_id = self.operation_batch_id(operations[-1])
        return batch_id, [
            operation for operation in operations
            if self.operation_batch_id(operation) == batch_id
        ]

    def inspect_undo_operation(self, operation):
        """Return the current restore readiness without changing any files."""
        original_path = Path(operation.get("source", ""))
        renamed_path = Path(operation.get("destination", ""))
        root_folder_text = str(operation.get("root_folder", "")).strip()
        root_folder = Path(root_folder_text) if root_folder_text else None

        if (
            not original_path.is_absolute() or
            not renamed_path.is_absolute() or
            original_path.parent != renamed_path.parent or
            original_path == renamed_path
        ):
            return "Blocked", "Unsafe or malformed operation-log entry"

        if root_folder is not None and (
            not root_folder.is_absolute() or
            not original_path.is_relative_to(root_folder) or
            not renamed_path.is_relative_to(root_folder)
        ):
            return "Blocked", "Path is outside the recorded scan folder"

        source_exists = self.path_exists_including_broken_link(original_path)
        destination_exists = self.path_exists_including_broken_link(renamed_path)

        if source_exists and not destination_exists:
            return "Stale", "Rename did not complete; log entry can be cleared"
        if not destination_exists:
            return "Blocked", "Renamed file is missing"
        if source_exists:
            return "Blocked", "Original filename already exists"

        return "Ready", "Ready to restore original filename"

    def preview_latest_batch(self):
        """Build a non-destructive restore preview for the latest batch only."""
        batch_id, operations = self.get_latest_batch()
        if self.last_log_error:
            return "", [], self.last_log_error
        if not operations:
            return "", [], "No recorded rename operations are available to undo."

        preview = []
        for operation in reversed(operations):
            status, detail = self.inspect_undo_operation(operation)
            preview.append({
                "operation": operation,
                "current_name": Path(operation.get("destination", "")).name,
                "original_name": Path(operation.get("source", "")).name,
                "status": status,
                "detail": detail,
            })

        return batch_id, preview, ""

    def preview_all_operations(self):
        """Build a non-destructive restore preview for every pending batch."""
        operations = self.load_operations()
        if self.last_log_error:
            return [], self.last_log_error
        if not operations:
            return [], "No recorded rename operations are available to undo."

        preview = []
        for operation in reversed(operations):
            status, detail = self.inspect_undo_operation(operation)
            preview.append({
                "operation": operation,
                "current_name": Path(operation.get("destination", "")).name,
                "original_name": Path(operation.get("source", "")).name,
                "status": status,
                "detail": detail,
                "batch_id": self.operation_batch_id(operation),
            })

        return preview, ""

    def undo_batch(self, batch_id, logger):
        """Undo one batch, or all pending batches when batch_id is None."""
        operations = self.load_operations()
        if self.last_log_error:
            return 0, 0, self.last_log_error

        batch_operations = operations if batch_id is None else [
            operation for operation in operations
            if self.operation_batch_id(operation) == batch_id
        ]
        if not batch_operations:
            return 0, 0, "The selected undo batch is no longer available."

        undone_count = 0
        failed_count = 0
        completed_operations = set()

        for operation in reversed(batch_operations):
            status, detail = self.inspect_undo_operation(operation)
            original_path = Path(operation.get("source", ""))
            renamed_path = Path(operation.get("destination", ""))

            if status == "Stale":
                completed_operations.add(id(operation))
                logger(f"Undo cleared stale entry: {original_path}")
                continue
            if status != "Ready":
                failed_count += 1
                logger(f"Undo skipped: {renamed_path} - {detail}")
                continue

            try:
                self.move_without_overwrite(renamed_path, original_path)
                completed_operations.add(id(operation))
                undone_count += 1
                logger(f"Undo: {renamed_path.name} -> {original_path.name}")
            except OSError as error:
                failed_count += 1
                logger(f"Undo failed: {renamed_path} - {error}")

        remaining_operations = [
            operation for operation in operations
            if id(operation) not in completed_operations
        ]
        save_ok, save_error = self.save_operations(remaining_operations)
        if not save_ok:
            return undone_count, failed_count, (
                f"Undo completed, but the operation log could not be updated: {save_error}"
            )

        return undone_count, failed_count, ""


class ExtensionRepairApp:
    """Tkinter UI layer for the Magic Number File Extension Repair Tool."""

    APP_TITLE = "Extension Fixer"
    VERSION = "Version 1.0.3"
    STRATEGY_LABELS = {
        1: "1 - Auto append serial number",
        2: "2 - Skip when duplicate name exists",
        3: "3 - Safe mode: forbid overwriting",
    }
    STRATEGY_NAMES = {
        1: "Auto append serial number",
        2: "Skip when duplicate name exists",
        3: "Safe mode: forbid overwriting",
    }

    def __init__(self, root):
        self.root = root
        self.root.title(self.APP_TITLE)

        self.settings_store = ApplicationSettings(Path.cwd() / "settings.json")
        self.settings = self.settings_store.load()
        self._fit_window_to_screen()

        self.format_config_path = Path.cwd() / "custom_magic_formats.json"
        self.detector = MagicNumberDetector(self.format_config_path)
        self.scanner = FileScanner(self.detector)
        self.operations = FileOperations(Path.cwd() / "operation_log.json")

        self.records = []
        self.scan_in_progress = False
        self.operation_in_progress = False
        self.confirmation_open = False
        self.config_window = None
        self.settings_window = None
        self.scan_iterator = None
        self.scan_thread = None
        self.scan_stop_event = None
        self.scan_event_queue = None
        self.accept_scan_events = False
        self.scan_root_path = None
        self.scan_processed_count = 0
        self.scan_session_token = 0
        self.scan_stopped_by_user = False
        self.stop_flush_pending = False
        self.pending_terminal = None
        self.table_refresh_token = 0
        self.table_refresh_in_progress = False
        self.pending_live_records = []
        self.checked_records = set()
        self.select_all_var = tk.BooleanVar(value=False)
        self.select_all_state = False

        self.folder_var = tk.StringVar(value=str(self.settings["last_folder"]))
        self.recursive_var = tk.BooleanVar(value=bool(self.settings["recursive_scan"]))
        self.repair_only_var = tk.BooleanVar(
            value=bool(self.settings["show_only_repair_items"])
        )
        self.backup_var = tk.BooleanVar(value=bool(self.settings["enable_backup"]))
        self.strategy_var = tk.StringVar(
            value=self.STRATEGY_LABELS[self.settings["duplicate_strategy"]]
        )
        self.size_limit_var = tk.StringVar(value=str(self.settings["max_size_mb"]))
        self.blacklist_var = tk.StringVar(value=str(self.settings["suffix_blacklist"]))

        self._configure_style()
        self._build_ui()
        self.update_action_buttons()
        loaded_formats, errors = self.detector.load_custom_formats()

        if loaded_formats:
            self.log(f"Loaded {len(loaded_formats)} custom magic-number format(s).")
        for error in errors:
            self.log(f"Format configuration warning: {error}")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _fit_window_to_screen(self):
        """Use Windows DPI scaling and responsive sizing."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        self.ui_scale = 1.0

        available_width = max(800, screen_width - 40)
        available_height = max(600, screen_height - 100)

        # Adaptive sizing: calculate the initial window from the current screen.
        # User window dimensions are intentionally not stored in settings.json.
        window_width = min(max(900, int(screen_width * 0.75)), available_width)
        window_height = min(max(600, int(screen_height * 0.75)), available_height)

        position_x = max(0, (screen_width - window_width) // 2)
        position_y = max(0, (screen_height - window_height) // 3)

        self.compact_layout = window_width < 1040

        self.root.minsize(800, 600)
        self.root.geometry(f"{window_width}x{window_height}+{position_x}+{position_y}")

    def scaled(self, value):
        """Tk handles DPI scaling; keep explicit sizes stable."""
        return max(1, int(value))

    def collect_settings(self):
        """Collect every software preference; format rules stay in their own file."""
        return {
            "last_folder": self.folder_var.get().strip(),
            "recursive_scan": self.recursive_var.get(),
            "show_only_repair_items": self.repair_only_var.get(),
            "enable_backup": self.backup_var.get(),
            "duplicate_strategy": self.get_strategy_code(),
            "max_size_mb": self.size_limit_var.get().strip(),
            "suffix_blacklist": self.blacklist_var.get().strip(),
        }

    def save_settings(self):
        """Persist GUI and scan preferences without mixing them with format rules."""
        success, error = self.settings_store.save(self.collect_settings())
        if not success:
            self.log(f"Could not save software settings: {error}")

    def on_close(self):
        # Never let a background worker publish into a destroyed Tk window.
        self.accept_scan_events = False
        self.scan_session_token += 1
        if self.scan_stop_event is not None:
            self.scan_stop_event.set()
        self.save_settings()
        self.root.destroy()

    def get_strategy_code(self):
        """Return the compact 1/2/3 strategy code selected in the GUI."""
        try:
            code = int(self.strategy_var.get().split(" ", 1)[0])
            return code if code in self.STRATEGY_NAMES else 1
        except (ValueError, AttributeError):
            return 1

    def get_strategy_name(self):
        """Translate the configured numeric strategy to the operation name."""
        return self.STRATEGY_NAMES[self.get_strategy_code()]

    def _configure_style(self):
        """Configure a soft modern ttk visual style."""
        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(background="#F5F5F5")
        body_font_size = self.scaled(10)
        section_font_size = self.scaled(11)

        style.configure(
            "TFrame",
            background="#F5F5F5"
        )
        style.configure(
            "Card.TLabelframe",
            background="#F5F5F5",
            borderwidth=1,
            relief="solid"
        )
        style.configure(
            "Card.TLabelframe.Label",
            background="#F5F5F5",
            foreground="#38506B",
            font=("Segoe UI", section_font_size, "bold")
        )
        style.configure(
            "Title.TLabel",
            background="#F5F5F5",
            foreground="#16324F",
            font=("Segoe UI", self.scaled(18), "bold")
        )
        style.configure(
            "Version.TLabel",
            background="#F5F5F5",
            foreground="#607D9A",
            font=("Segoe UI", body_font_size)
        )
        style.configure(
            "TLabel",
            background="#F5F5F5",
            foreground="#34495E",
            font=("Segoe UI", body_font_size)
        )
        style.configure(
            "TCheckbutton",
            background="#F5F5F5",
            font=("Segoe UI", body_font_size)
        )
        style.configure(
            "TButton",
            font=("Segoe UI", body_font_size),
            padding=(8, 4)
        )
        style.configure(
            "Accent.TButton",
            foreground="white",
            background="#377DAB",
            padding=(8, 4)
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#2D6E99")]
        )
        style.configure(
            "Danger.TButton",
            foreground="white",
            background="#C75B4A",
            padding=(8, 4)
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#A9493B")]
        )
        style.configure(
            "Treeview",
            rowheight=self.scaled(32),
            font=("Segoe UI", body_font_size),
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground="#2D3E50"
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", body_font_size, "bold"),
            background="#DCE8F3",
            foreground="#263D56",
            relief="flat",
            padding=(self.scaled(6), self.scaled(7))
        )
        style.map(
            "Treeview",
            background=[("selected", "#B9D8EE")],
            foreground=[("selected", "#17324D")]
        )

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=self.scaled(14))
        main_frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(3, weight=1)

        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        title_frame.columnconfigure(0, weight=1)

        ttk.Label(
            title_frame,
            text=self.APP_TITLE,
            style="Title.TLabel"
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            title_frame,
            text="Magic-number based extension repair tool",
            style="Version.TLabel"
        ).grid(row=1, column=0, sticky="w")

        ttk.Label(
            title_frame,
            text=self.VERSION,
            style="Version.TLabel"
        ).grid(row=0, column=1, sticky="e")

        self._build_path_panel(main_frame)
        self._build_table_panel(main_frame)
        self._build_bottom_panel(main_frame)

    def _build_path_panel(self, parent):
        path_frame = ttk.LabelFrame(
            parent,
            text="Folder Selection",
            style="Card.TLabelframe",
            padding=10
        )
        path_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        path_frame.columnconfigure(1, weight=1)

        ttk.Label(path_frame, text="Target folder:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )

        self.path_entry = ttk.Entry(path_frame, textvariable=self.folder_var)
        self.path_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        ttk.Button(
            path_frame,
            text="Settings…",
            command=self.open_settings_window
        ).grid(row=0, column=2, padx=(0, 8))

        ttk.Button(
            path_frame,
            text="Select Folder",
            command=self.select_folder
        ).grid(row=0, column=3, padx=(0, 8))

        self.scan_button = ttk.Button(
            path_frame,
            text="▶  Scan Files",
            style="Accent.TButton",
            command=self.scan_files
        )
        self.scan_button.grid(row=0, column=4)

        ttk.Button(
            path_frame,
            text="⟳ Refresh",
            command=self.manual_refresh_table
        ).grid(row=0, column=5, padx=(8, 0))

    def _build_table_panel(self, parent):
        table_frame = ttk.LabelFrame(
            parent,
            text="Scan Results",
            style="Card.TLabelframe",
            padding=8
        )
        table_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = (
            "select",
            "file_name",
            "current_extension",
            "detected_extension",
            "status",
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            # Checkbox state is the only source of action selection. Disabling
            # native row selection avoids a highlighted row appearing as if it
            # will be included in Preview or Execute Repair.
            selectmode="none"
        )
        self.tree.bind("<Button-1>", self.toggle_checkbox)

        self.tree.heading("select", text="☐", command=self.toggle_all_checkbox)
        self.tree.heading("file_name", text="File Name (Relative Path)")
        self.tree.heading("current_extension", text="Current Extension")
        self.tree.heading("detected_extension", text="Detected Real Extension")
        self.tree.heading("status", text="Status")

        self.tree.column("select", width=self.scaled(45), minwidth=self.scaled(45), anchor="center")
        self.tree.column("file_name", width=self.scaled(450), minwidth=self.scaled(220), anchor="w")
        self.tree.column("current_extension", width=self.scaled(135), minwidth=self.scaled(105), anchor="center")
        self.tree.column("detected_extension", width=self.scaled(165), minwidth=self.scaled(140), anchor="center")
        self.tree.column("status", width=self.scaled(270), minwidth=self.scaled(200), anchor="w")

        self.tree.tag_configure("repair", background="#FFF0D9", foreground="#9A4D00")
        self.tree.tag_configure("normal", background="#EAF6EC", foreground="#22653A")
        self.tree.tag_configure("warning", background="#F7F7F7", foreground="#626D78")
        self.tree.tag_configure("error", background="#FDE9E7", foreground="#A2352A")
        self.tree.tag_configure("alternate", background="#F6F9FC")

        vertical_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview
        )
        horizontal_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview
        )

        self.tree.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set
        )

        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")

    def _build_bottom_panel(self, parent):
        bottom_frame = ttk.Frame(parent)
        bottom_frame.grid(row=3, column=0, sticky="nsew")
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.rowconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(
            bottom_frame,
            text="Operation Log",
            style="Card.TLabelframe",
            padding=8
        )
        log_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=8,
            wrap="word",
            background="#FFFFFF",
            foreground="#34495E",
            relief="flat",
            font=("Consolas", self.scaled(9))
        )
        log_scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")

        button_frame = ttk.LabelFrame(
            bottom_frame,
            text="Actions",
            style="Card.TLabelframe",
            padding=10
        )
        button_frame.grid(row=0, column=1, sticky="ns")

        ttk.Button(
            button_frame,
            text="↓ Export CSV Report",
            command=self.export_report
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.preview_button = ttk.Button(
            button_frame,
            text="🔍 Preview Repairs",
            style="Accent.TButton",
            command=self.preview_repairs
        )
        self.preview_button.grid(row=1, column=0, sticky="ew", pady=6)

        self.repair_button = ttk.Button(
            button_frame,
            text="⚙ Execute Repair",
            style="Danger.TButton",
            command=self.execute_repairs
        )
        self.repair_button.grid(row=2, column=0, sticky="ew", pady=6)

        ttk.Button(
            button_frame,
            text="↶ Undo Recorded Changes",
            command=self.undo_repairs
        ).grid(row=3, column=0, sticky="ew", pady=(6, 0))

    def update_action_buttons(self):
        """Enable repair actions only when currently displayed files are selected.

        Selection is stored by file path. Validate it against the current
        records so stale selections from previous scans or refreshes cannot
        incorrectly lock or unlock action buttons.
        """
        current_paths = {
            record.get("path")
            for record in self.records
            if record.get("path")
        }

        active_selection = self.checked_records.intersection(current_paths)
        has_selection = bool(active_selection)
        actions_available = (
            has_selection and
            not self.scan_in_progress and
            not self.operation_in_progress
        )

        if hasattr(self, "preview_button"):
            self.preview_button.configure(
                state="normal" if actions_available else "disabled"
            )

        if hasattr(self, "repair_button"):
            self.repair_button.configure(
                state="normal" if actions_available else "disabled"
            )

    def log(self, message):
        """Append a message to the visible log panel."""
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def open_settings_window(self):
        """Show one focused window for all software preferences."""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        original_values = {
            "recursive": self.recursive_var.get(),
            "repair_only": self.repair_only_var.get(),
            "backup": self.backup_var.get(),
            "strategy": self.strategy_var.get(),
            "size_limit": self.size_limit_var.get(),
            "blacklist": self.blacklist_var.get(),
        }

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Software Settings")
        self.settings_window.resizable(False, False)
        self.settings_window.transient(self.root)
        self.settings_window.columnconfigure(0, weight=1)

        scan_frame = ttk.LabelFrame(
            self.settings_window,
            text="Scan Settings",
            style="Card.TLabelframe",
            padding=12
        )
        scan_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))

        ttk.Checkbutton(
            scan_frame,
            text="Scan sub-directories recursively",
            variable=self.recursive_var
        ).grid(row=0, column=0, sticky="w", pady=3)

        ttk.Checkbutton(
            scan_frame,
            text="Show only files requiring repair",
            variable=self.repair_only_var,
            command=self.refresh_table
        ).grid(row=1, column=0, sticky="w", pady=3)

        protection_frame = ttk.LabelFrame(
            self.settings_window,
            text="Repair and Protection Settings",
            style="Card.TLabelframe",
            padding=12
        )
        protection_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        protection_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            protection_frame,
            text="Back up originals before rename",
            variable=self.backup_var
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 7))

        ttk.Label(protection_frame, text="Duplicate strategy:").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Combobox(
            protection_frame,
            textvariable=self.strategy_var,
            state="readonly",
            values=tuple(self.STRATEGY_LABELS.values()),
            width=31
        ).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(protection_frame, text="Maximum size (MB, 0 = unlimited):").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(protection_frame, textvariable=self.size_limit_var).grid(
            row=2, column=1, sticky="ew", pady=4
        )

        ttk.Label(protection_frame, text="Suffix blacklist:").grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(protection_frame, textvariable=self.blacklist_var).grid(
            row=3, column=1, sticky="ew", pady=4
        )

        format_frame = ttk.LabelFrame(
            self.settings_window,
            text="Format Definitions",
            style="Card.TLabelframe",
            padding=12
        )
        format_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=8)
        format_frame.columnconfigure(0, weight=1)

        ttk.Label(
            format_frame,
            text="Magic-number signatures are stored separately in custom_magic_formats.json."
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            format_frame,
            text="Configure Formats…",
            command=self.open_format_configuration
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))

        button_frame = ttk.Frame(self.settings_window, padding=(14, 6, 14, 14))
        button_frame.grid(row=3, column=0, sticky="ew")
        button_frame.columnconfigure(0, weight=1)

        def close_window(restore=False):
            if restore:
                self.recursive_var.set(original_values["recursive"])
                self.repair_only_var.set(original_values["repair_only"])
                self.backup_var.set(original_values["backup"])
                self.strategy_var.set(original_values["strategy"])
                self.size_limit_var.set(original_values["size_limit"])
                self.blacklist_var.set(original_values["blacklist"])
                self.refresh_table()

            self.settings_window.destroy()
            self.settings_window = None

        def save_from_window():
            success, error = self.settings_store.save(self.collect_settings())

            if success:
                self.log("Software settings saved to settings.json.")
                messagebox.showinfo(
                    "Settings Saved",
                    "Software settings have been saved successfully.",
                    parent=self.settings_window
                )
                close_window()
            else:
                messagebox.showerror(
                    "Settings Save Error",
                    f"Could not save software settings:\n{error}",
                    parent=self.settings_window
                )

        ttk.Button(
            button_frame,
            text="Cancel",
            command=lambda: close_window(restore=True)
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(
            button_frame,
            text="Save Settings",
            style="Accent.TButton",
            command=save_from_window
        ).grid(row=0, column=2, padx=(8, 0))

        self.settings_window.protocol("WM_DELETE_WINDOW", lambda: close_window(restore=True))

    def select_folder(self):
        selected_folder = filedialog.askdirectory(
            title="Select Folder to Scan",
            initialdir=self.folder_var.get() or str(Path.cwd())
        )

        if selected_folder:
            self.folder_var.set(selected_folder)
            self.save_settings()

    def _validate_folder(self):
        folder_text = self.folder_var.get().strip()

        if not folder_text:
            messagebox.showwarning("Folder Required", "Please select a folder first.")
            return None

        folder_path = Path(folder_text)

        if not folder_path.exists() or not folder_path.is_dir():
            messagebox.showerror(
                "Invalid Folder",
                "The selected path does not exist or is not a folder."
            )
            return None

        return folder_path

    def _get_size_limit(self):
        try:
            size_limit = float(self.size_limit_var.get().strip())

            if not (0 <= size_limit <= 1000000):
                raise ValueError

            return size_limit
        except ValueError:
            messagebox.showerror(
                "Invalid Size Limit",
                "Maximum size must be a non-negative number in MB."
            )
            return None

    def open_format_configuration(self):
        """Open the persistent JSON editor for user-defined magic formats."""
        if self.config_window and self.config_window.winfo_exists():
            self.config_window.lift()
            self.config_window.focus_force()
            return

        self.config_window = tk.Toplevel(self.root)
        self.config_window.title("Magic-Number Format Configuration")
        self.config_window.minsize(700, 480)
        self.config_window.geometry("760x540")
        self.config_window.transient(self.root)
        self.config_window.columnconfigure(0, weight=1)
        self.config_window.rowconfigure(1, weight=1)

        instructions = (
            "This JSON file defines every supported format. A signature is hexadecimal; "
            "offset is measured from byte 0 and must remain within the first 16 bytes. "
            "Use 'signatures' for multiple required conditions (such as RIFF plus WEBP)."
        )
        ttk.Label(
            self.config_window,
            text=instructions,
            wraplength=720,
            justify="left",
            padding=(12, 12, 12, 6)
        ).grid(row=0, column=0, sticky="ew")

        editor_frame = ttk.Frame(self.config_window, padding=(12, 0, 12, 8))
        editor_frame.grid(row=1, column=0, sticky="nsew")
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        editor = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=("Consolas", 10),
            background="#FFFFFF",
            foreground="#263D56",
            relief="solid",
            borderwidth=1
        )
        editor_scrollbar = ttk.Scrollbar(editor_frame, orient="vertical", command=editor.yview)
        editor.configure(yscrollcommand=editor_scrollbar.set)
        editor.grid(row=0, column=0, sticky="nsew")
        editor_scrollbar.grid(row=0, column=1, sticky="ns")

        default_configuration = {"formats": []}

        try:
            if self.format_config_path.exists():
                with open(self.format_config_path, "r", encoding="utf-8") as file_handle:
                    editor.insert("1.0", file_handle.read())
            else:
                editor.insert("1.0", json.dumps(default_configuration, indent=2))
        except OSError as error:
            editor.insert("1.0", json.dumps(default_configuration, indent=2))
            self.log(f"Could not read format configuration: {error}")

        button_frame = ttk.Frame(self.config_window, padding=(12, 0, 12, 12))
        button_frame.grid(row=2, column=0, sticky="ew")
        button_frame.columnconfigure(0, weight=1)

        def close_window():
            self.config_window.destroy()
            self.config_window = None

        def save_configuration():
            success, result_message = self.detector.save_custom_config(
                editor.get("1.0", "end-1c")
            )

            if success:
                self.log(f"Format configuration saved: {result_message}")
                messagebox.showinfo("Configuration Saved", result_message, parent=self.config_window)
                close_window()
            else:
                messagebox.showerror(
                    "Configuration Error",
                    result_message,
                    parent=self.config_window
                )

        ttk.Label(
            button_frame,
            text=f"Config file: {self.format_config_path.name}"
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(
            button_frame,
            text="Cancel",
            command=close_window
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Save Configuration",
            style="Accent.TButton",
            command=save_configuration
        ).grid(row=0, column=2, padx=(8, 0))

        self.config_window.protocol("WM_DELETE_WINDOW", close_window)

    def reload_custom_formats(self):
        """Reload the JSON configuration so external edits apply to each scan."""
        loaded_formats, errors = self.detector.load_custom_formats()

        for error in errors:
            self.log(f"Format configuration warning: {error}")

        return loaded_formats, errors

    def scan_files(self):
        """Scan the selected folder, resetting all prior result rows."""
        if self.scan_in_progress or self.operation_in_progress:
            self.log("A scan or file operation is already in progress.")
            return

        root_path = self._validate_folder()
        if not root_path:
            return

        max_size_mb = self._get_size_limit()
        if max_size_mb is None:
            return

        self.save_settings()

        self.scan_session_token += 1
        scan_token = self.scan_session_token
        self.scan_stopped_by_user = False
        self.scan_in_progress = True
        self.scan_button.configure(
            text="Stop Scan",
            style="Danger.TButton",
            command=self.stop_scan
        )

        # A scan is a new selection session. Retaining checkbox paths from an
        # earlier scan could silently re-select files that still have the same
        # paths, which is unsafe for a rename-oriented workflow.
        self.checked_records.clear()
        self.select_all_state = False
        self.select_all_var.set(False)
        self.records = []
        self.update_action_buttons()
        self.refresh_table()

        self.reload_custom_formats()

        blacklist = self.scanner.parse_blacklist(self.blacklist_var.get())
        self.log(f"Scanning folder: {root_path}")
        self.log(
            f"Recursive: {'enabled' if self.recursive_var.get() else 'disabled'} | "
            f"Size limit: {max_size_mb:g} MB"
        )

        self.scan_root_path = root_path
        self.scan_processed_count = 0
        self.scan_repair_count = 0
        self.accept_scan_events = True
        self.scan_event_queue = queue.Queue(maxsize=5000)
        self.scan_stop_event = threading.Event()
        worker = ScanWorker(
            scanner=self.scanner,
            event_queue=self.scan_event_queue,
            stop_event=self.scan_stop_event,
            scan_token=scan_token,
            root_folder=root_path,
            recursive=self.recursive_var.get(),
            max_size_mb=max_size_mb,
            blacklist=blacklist,
        )
        self.scan_thread = threading.Thread(
            target=worker.run,
            name=f"ExtensionFixerScan-{scan_token}",
            daemon=True,
        )
        self.scan_thread.start()
        self.root.after(100, lambda: self.process_scan_events(scan_token))

    def stop_scan(self):
        """Request cancellation and keep operations locked until worker exit."""
        if not self.scan_in_progress:
            return

        # Ignore repeated programmatic requests while the disabled Stop button
        # is already waiting for the same worker to terminate.
        if self.scan_stop_event is not None and self.scan_stop_event.is_set():
            return

        self.scan_stopped_by_user = True
        self.scan_button.configure(state="disabled", text="Stopping...")
        self.log("Stopping scan... cancelling current scan session.")

        # Invalidate the current session immediately so late worker events
        # cannot affect a future scan.
        self.scan_session_token += 1
        self.accept_scan_events = False

        if self.scan_stop_event is not None:
            self.scan_stop_event.set()

        # Drop queued events from the cancelled worker. The user requested a
        # hard stop, not a drain/finish operation.
        if self.scan_event_queue is not None:
            try:
                while True:
                    self.scan_event_queue.get_nowait()
            except queue.Empty:
                pass

        # scan_in_progress deliberately remains True. This blocks Scan,
        # Execute Repair, and Undo until the exact worker reports that it is no
        # longer alive.
        self.update_action_buttons()
        worker_thread = self.scan_thread
        if worker_thread is None or not worker_thread.is_alive():
            self.finish_cancelled_scan(worker_thread)
        else:
            self.root.after(
                50,
                lambda: self.wait_for_scan_thread_stop(worker_thread)
            )

    def wait_for_scan_thread_stop(self, worker_thread):
        """Poll without blocking Tkinter until the cancelled worker exits."""
        if worker_thread is not self.scan_thread:
            return

        if worker_thread.is_alive():
            self.root.after(
                50,
                lambda: self.wait_for_scan_thread_stop(worker_thread)
            )
            return

        self.finish_cancelled_scan(worker_thread)

    def finish_cancelled_scan(self, worker_thread):
        """Unlock the application after confirmed cancellation completion."""
        if worker_thread is not None and worker_thread is not self.scan_thread:
            return

        # The worker may have emitted one final stopped event just before
        # exiting. It belongs to the invalidated session and must not leak into
        # a later scan.
        if self.scan_event_queue is not None:
            try:
                while True:
                    self.scan_event_queue.get_nowait()
            except queue.Empty:
                pass

        self.scan_in_progress = False
        self.scan_thread = None
        self.scan_stop_event = None
        self.scan_event_queue = None
        self.pending_terminal = None
        self.reset_scan_button()
        self.update_action_buttons()
        self.log(
            f"Scan cancelled after worker exit. "
            f"Retained {len(self.records):,} processed result(s)."
        )


    def reset_scan_button(self):
        """Restore the primary scan action after scan completion or cancellation."""
        self.scan_button.configure(
            text="▶  Scan Files",
            style="Accent.TButton",
            command=self.scan_files,
            state="normal"
        )

    def process_scan_events(self, scan_token):
        """Drain worker events in bounded batches on Tkinter's main thread."""
        if (
            scan_token != self.scan_session_token or
            self.scan_event_queue is None
        ):
            return

        processed_events = 0
        terminal_event = False
        new_records = []

        while processed_events < 300:
            try:
                event_type, event_token, payload = self.scan_event_queue.get_nowait()
            except queue.Empty:
                break

            if event_token != scan_token:
                continue

            processed_events += 1

            if event_type == "record":
                payload.setdefault("record_id", uuid.uuid4().hex)
                self.records.append(payload)
                new_records.append(payload)
            elif event_type == "progress":
                self.scan_processed_count = payload["processed"]
                self.scan_repair_count = payload["repair_count"]
                self.log(
                    f"Scanning… checked {self.scan_processed_count:,} file(s); "
                    f"{self.scan_repair_count:,} repair candidate(s)."
                )
            elif event_type == "log":
                self.log(payload)
            elif event_type == "completed":
                self.pending_terminal = (payload, False)
                terminal_event = True
                break
            elif event_type == "stopped":
                self.pending_terminal = (payload, True)
                terminal_event = True
                break
            elif event_type == "error":
                self.finish_scan({}, stopped=False)
                self.log(f"Unexpected scan error: {payload}")
                messagebox.showerror("Scan Error", f"An unexpected error occurred:\n{payload}")
                terminal_event = True
                break

        # Add only records received in this queue pass. Rebuilding every row
        # repeatedly makes large scans progressively slower.
        self.append_live_records(new_records)

        # After worker termination, drain any remaining queued events before
        # finalizing the scan summary.
        if terminal_event and self.pending_terminal is not None:
            remaining = not self.scan_event_queue.empty() if self.scan_event_queue else False
            if remaining:
                self.root.after(50, lambda: self.process_scan_events(scan_token))
                return
            summary, stopped = self.pending_terminal
            self.pending_terminal = None
            self.finish_scan(summary, stopped=stopped)
            return

        if not terminal_event and self.scan_in_progress:
            self.root.after(100, lambda: self.process_scan_events(scan_token))

    def finish_scan(self, summary, stopped):
        """Finalize a worker scan after all relevant queue events are handled."""
        if (
            self.scan_stopped_by_user and
            self.scan_stop_event is not None and
            self.scan_stop_event.is_set()
        ):
            # A Stop request won a race with the worker's terminal event. The
            # cancellation poll owns final cleanup and must remain the only
            # path that unlocks the application.
            return

        worker_thread = self.scan_thread
        if worker_thread is not None and worker_thread.is_alive():
            # The terminal queue event is emitted immediately before run()
            # returns. Confirm the thread has actually exited before unlocking
            # file operations or allowing another scan.
            self.root.after(25, lambda: self.finish_scan(summary, stopped))
            return

        self.accept_scan_events = False
        self.scan_in_progress = False
        self.scan_thread = None
        self.scan_stop_event = None
        self.scan_event_queue = None
        self.reset_scan_button()
        self.stop_flush_pending = False

        # All record events are appended before the terminal event is handled.
        # A full Treeview rebuild here would duplicate work and stall large
        # scans at the moment they complete.
        if not self.table_refresh_in_progress:
            self.update_select_all_header()
            self.update_action_buttons()

        processed_count = summary.get("processed", len(self.records))
        repair_count = summary.get(
            "repair_count",
            sum(1 for record in self.records if record["status"] == "Repair required")
        )
        self.scan_processed_count = processed_count
        self.scan_repair_count = repair_count

        if stopped:
            self.scan_stopped_by_user = True
            self.log(
                f"Scan stopped: {processed_count:,} file(s) processed; "
                f"{repair_count:,} file(s) require repair."
            )
        else:
            self.log(
                f"Scan complete: {processed_count:,} file(s) found; "
                f"{repair_count:,} file(s) require repair."
            )

    def _record_visible(self, record):
        """Apply the Show-only-repair-items UI filter."""
        if self.repair_only_var.get():
            return record["status"] == "Repair required"

        return True

    def _record_tag(self, record, visible_index):
        """Choose a visual status style for one Treeview row."""
        status = record["status"]

        if status == "Repair required":
            return "repair"

        if status.startswith("Error"):
            return "error"

        if status.startswith("Normal") or status == "Repaired successfully":
            return "normal"

        if visible_index % 2 == 1:
            return "alternate"

        return "warning"

    def manual_refresh_table(self):
        """Manually refresh visible scan results without restarting the scan."""
        self.refresh_table()
        self.log("Scan results refreshed.")

    def refresh_table(self):
        """Rebuild the table only for explicit refreshes or data changes."""
        self.table_refresh_token += 1
        refresh_token = self.table_refresh_token

        # Every record that exists now is included in this immutable snapshot.
        # Records arriving later are buffered and appended when the rebuild is
        # complete, preventing duplicate item IDs and preserving row order.
        record_snapshot = tuple(self.records)
        self.pending_live_records = []
        self.table_refresh_in_progress = True

        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        self.update_select_all_header()
        self.table_record_iterator = iter(record_snapshot)
        self.table_visible_index = 0
        self.root.after_idle(lambda: self.populate_table_chunk(refresh_token))

    def populate_table_chunk(self, refresh_token):
        """Insert a bounded number of visible rows before returning to Tkinter."""
        if refresh_token != self.table_refresh_token:
            return

        rows_per_chunk = 250
        try:
            for _ in range(rows_per_chunk):
                record = next(self.table_record_iterator)
                if not self._record_visible(record):
                    continue

                self.insert_table_record(record)
        except StopIteration:
            self.table_refresh_in_progress = False
            pending_records = self.pending_live_records
            self.pending_live_records = []
            self.append_live_records(pending_records)
            self.update_select_all_header()
            self.update_action_buttons()
            return

        self.root.after_idle(lambda: self.populate_table_chunk(refresh_token))

    def insert_table_record(self, record):
        """Insert one visible record and return whether a row was added."""
        if not self._record_visible(record):
            return False

        item_id = record.get("path", "")
        if not item_id or self.tree.exists(item_id):
            return False

        self.tree.insert(
            "",
            "end",
            iid=item_id,
            values=(
                "☑" if item_id in self.checked_records else "☐",
                record["relative_path"],
                record["current_extension"] or "(none)",
                record["detected_extension"] or "(unknown)",
                record["status"],
            ),
            tags=(self._record_tag(record, self.table_visible_index),)
        )
        self.table_visible_index += 1
        return True

    def append_live_records(self, records):
        """Append a queue batch without rebuilding rows already displayed."""
        if not records:
            return

        if self.table_refresh_in_progress:
            self.pending_live_records.extend(records)
            return

        inserted_count = 0
        for record in records:
            if self.insert_table_record(record):
                inserted_count += 1

        if inserted_count:
            # New rows start unchecked. If every prior visible row was checked,
            # the header becomes indeterminate without scanning the full result
            # list on every live batch.
            if self.tree.heading("select", "text") == "☑":
                self.select_all_state = False
                self.tree.heading(
                    "select",
                    text="▣",
                    command=self.toggle_all_checkbox
                )

    def update_select_all_header(self):
        """Synchronize the header checkbox with current visible rows.

        States:
        ☐ no visible rows selected
        ☑ all visible rows selected
        ▣ some visible rows selected
        """
        visible_paths = {
            record.get("path")
            for record in self.records
            if self._record_visible(record) and record.get("path")
        }

        selected_paths = visible_paths.intersection(self.checked_records)

        if not visible_paths or not selected_paths:
            symbol = "☐"
            self.select_all_state = False
        elif selected_paths == visible_paths:
            symbol = "☑"
            self.select_all_state = True
        else:
            symbol = "▣"
            self.select_all_state = False

        self.tree.heading("select", text=symbol, command=self.toggle_all_checkbox)

    def toggle_all_checkbox(self):
        """Toggle selection of all currently visible rows.

        File paths are the only selection source of truth. The Treeview is
        updated in-place so scrolling and large-list selection remain stable.
        """
        visible_records = [
            record for record in self.records
            if self._record_visible(record) and record.get("path")
        ]

        if not visible_records:
            return

        visible_paths = {record.get("path") for record in visible_records}
        all_selected = visible_paths.issubset(self.checked_records)

        if all_selected:
            self.checked_records.difference_update(visible_paths)
        else:
            self.checked_records.update(visible_paths)

        for path in visible_paths:
            if self.tree.exists(path):
                values = list(self.tree.item(path, "values"))
                if values:
                    values[0] = "☑" if path in self.checked_records else "☐"
                    self.tree.item(path, values=values)

        self.update_select_all_header()
        self.update_action_buttons()

    def toggle_checkbox(self, event):
        """Toggle one row checkbox without rebuilding the Treeview."""
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item_id or column != "#1":
            return

        file_path = item_id
        if not file_path:
            return

        if file_path in self.checked_records:
            self.checked_records.remove(file_path)
            checked = "☐"
        else:
            self.checked_records.add(file_path)
            checked = "☑"

        values = list(self.tree.item(item_id, "values"))
        if values:
            values[0] = checked
            self.tree.item(item_id, values=values)

        self.update_select_all_header()
        self.update_action_buttons()

        return "break"

    def _get_selected_or_repair_records(self):
        """
        Return user-selected repair candidates only.

        Selection is independent from repair status because the result table
        allows users to inspect and select any scanned file.  Files that do
        not need repair are intentionally ignored during repair operations.
        This prevents accidental operations on normal/skipped files while
        still allowing users to select mixed result rows.
        """
        checked_records = [
            record for record in self.records
            if record.get("path") in self.checked_records
        ]

        if checked_records:
            repair_records = [
                record for record in checked_records
                if record.get("status") == "Repair required"
            ]

            ignored_count = len(checked_records) - len(repair_records)
            if ignored_count:
                self.log(
                    f"Ignored {ignored_count} selected file(s) because they "
                    "do not require repair."
                )

            return repair_records, True

        # No checkbox selection means the user has not chosen any files.
        # Do not silently fall back to every repair candidate.
        return [], True

    def preview_repairs(self):
        """
        Preview rename targets without modifying the file system.

        This function does not create backups, files, folders, or log entries.
        """
        if self.operation_in_progress:
            self.log("An operation is already in progress.")
            return

        records, using_selection = self._get_selected_or_repair_records()

        if not records:
            messagebox.showinfo(
                "Nothing to Preview",
                "Select files using the checkbox before previewing repairs."
            )
            return

        _, conflicts, planning_error = self.operations.plan_renames(
            records,
            self.get_strategy_name()
        )

        self.log(
            "Preview for "
            f"{'selected files' if using_selection else 'all repair-required files'}:"
        )

        if planning_error:
            self.log(planning_error)
            messagebox.showwarning("Preview Blocked", planning_error)
            return

        for record in records:
            planned_path = record.get("planned_path", "")

            if planned_path:
                self.log(
                    f"Preview: {record['relative_path']} -> "
                    f"{Path(planned_path).name}"
                )
            else:
                self.log(f"Preview skip: {record['relative_path']}")

        if conflicts:
            self.log(f"Conflict handling applied to {len(conflicts)} item(s).")

        self.refresh_table()
        messagebox.showinfo(
            "Preview Complete",
            f"Preview generated for {len(records)} file(s).\n"
            "No files or folders were modified."
        )

    def execute_repairs(self):
        """Confirm and execute safe file-name repairs."""
        if self.operation_in_progress or self.scan_in_progress:
            self.log("A scan or operation is already in progress.")
            return

        root_path = self._validate_folder()
        if not root_path:
            return

        max_size_mb = self._get_size_limit()
        if max_size_mb is None:
            return

        records, using_selection = self._get_selected_or_repair_records()

        if not records:
            messagebox.showinfo(
                "Nothing to Repair",
                "There are no selected files requiring repair."
            )
            return

        if self.confirmation_open:
            return

        selection_description = (
            "the selected files" if using_selection else "all repair-required files"
        )
        backup_description = (
            "A backup folder will be created before renaming."
            if self.backup_var.get()
            else "Backup is disabled."
        )

        self.confirmation_open = True
        try:
            confirmed = messagebox.askyesno(
                "Confirm File Rename",
                f"You are about to rename {len(records)} file(s) from "
                f"{selection_description}.\n\n"
                f"Strategy: {self.get_strategy_name()}\n"
                f"{backup_description}\n\n"
                "Only file names will be changed. Continue?",
                icon="warning"
            )
        finally:
            self.confirmation_open = False

        if not confirmed:
            self.log("Repair operation cancelled by user.")
            return

        self.operation_in_progress = True

        try:
            result = self.operations.rename_records(
                records=records,
                root_path=root_path,
                strategy=self.get_strategy_name(),
                enable_backup=self.backup_var.get(),
                max_size_mb=max_size_mb,
                logger=self.log
            )

            if result.get("renamed", 0) > 0:
                self.checked_records.clear()
                self.select_all_state = False
                self.select_all_var.set(False)

            self.refresh_table()
            self.update_action_buttons()

            if result["message"]:
                self.log(result["message"])
                messagebox.showwarning("Repair Not Completed", result["message"])
                return

            summary = (
                f"Repair completed.\n\n"
                f"Renamed: {result['renamed']}\n"
                f"Skipped: {result['skipped']}\n"
                f"Failed: {result['failed']}"
            )

            self.log(summary.replace("\n", " | "))
            messagebox.showinfo("Repair Complete", summary)

        except Exception as error:
            self.log(f"Unexpected repair error: {error}")
            messagebox.showerror(
                "Repair Error",
                f"An unexpected error occurred:\n{error}"
            )
        finally:
            self.operation_in_progress = False
            # This also runs for early returns such as safe-mode conflicts,
            # backup setup failures, and protected/corrupt operation logs.
            # Recalculate from current checkbox state after unlocking.
            self.update_action_buttons()

        # A manually stopped scan must stay stopped. Preserve its partial
        # results instead of silently starting a new full scan after repair.
        if self.folder_var.get().strip() and not self.scan_stopped_by_user:
            self.scan_files()
        else:
            self.refresh_table()
            self.update_action_buttons()

    def export_report(self):
        """Export all current scan records, including hidden filtered entries."""
        if not self.records:
            messagebox.showinfo(
                "No Results",
                "Scan a folder before exporting a report."
            )
            return

        initial_directory = self.folder_var.get() or str(Path.cwd())
        report_path = filedialog.asksaveasfilename(
            title="Export Scan Report",
            initialdir=initial_directory,
            initialfile="extensionfixer_report.csv",
            defaultextension=".csv",
            filetypes=(("CSV Files", "*.csv"), ("All Files", "*.*"))
        )

        if not report_path:
            return

        try:
            with open(report_path, "w", newline="", encoding="utf-8-sig") as file_handle:
                writer = csv.DictWriter(
                    file_handle,
                    fieldnames=(
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
                )
                writer.writeheader()

                for record in self.records:
                    writer.writerow({
                        "relative_path": record["relative_path"],
                        "full_path": record["path"],
                        "file_name": record["file_name"],
                        "current_extension": record["current_extension"],
                        "detected_real_extension": record["detected_extension"],
                        "size_bytes": record["size_bytes"],
                        "size_display": record["size_display"],
                        "status": record["status"],
                        "planned_target": record["planned_path"],
                        "error": record["error"],
                    })

            self.log(f"CSV report exported: {report_path}")
            messagebox.showinfo("Export Complete", "CSV report exported successfully.")

        except OSError as error:
            self.log(f"CSV export failed: {error}")
            messagebox.showerror("Export Failed", f"Could not export report:\n{error}")

    def undo_repairs(self):
        """Preview and restore only the most recent recorded repair batch."""
        if self.operation_in_progress or self.scan_in_progress:
            self.log("A scan or operation is already in progress.")
            return

        batch_id, preview, error_message = self.operations.preview_latest_batch()
        if error_message:
            self.log(error_message)
            messagebox.showerror("Undo Unavailable", error_message)
            return

        self.show_undo_preview(batch_id, preview, restore_all=False)

    def show_undo_preview(self, batch_id, preview, restore_all=False):
        """Display a restore scope and require confirmation before any rename."""
        preview_window = tk.Toplevel(self.root)
        scope_name = "All Recorded Batches" if restore_all else "Latest Repair Batch"
        preview_window.title(f"Undo Preview — {scope_name}")
        preview_window.minsize(760, 390)
        preview_window.geometry("900x480")
        preview_window.transient(self.root)
        preview_window.grab_set()
        preview_window.columnconfigure(0, weight=1)
        preview_window.rowconfigure(1, weight=1)

        ready_count = sum(1 for item in preview if item["status"] == "Ready")
        ttk.Label(
            preview_window,
            text=(
                f"{scope_name}: {batch_id if not restore_all else 'all pending records'} "
                f"| {ready_count} of {len(preview)} item(s) are ready to restore."
            ),
            padding=(12, 12, 12, 6)
        ).grid(row=0, column=0, sticky="w")

        table_frame = ttk.Frame(preview_window, padding=(12, 0, 12, 8))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        table = ttk.Treeview(
            table_frame,
            columns=("current", "original", "batch", "status", "detail"),
            show="headings",
            height=12
        )
        for column, label, width in (
            ("current", "Current Name", 210),
            ("original", "Restore To", 210),
            ("batch", "Batch", 150),
            ("status", "Status", 100),
            ("detail", "Details", 250),
        ):
            table.heading(column, text=label)
            table.column(column, width=width, minwidth=90, anchor="w")

        table.tag_configure("ready", background="#EAF6EC", foreground="#22653A")
        table.tag_configure("blocked", background="#FDE9E7", foreground="#A2352A")
        table.tag_configure("stale", background="#FFF0D9", foreground="#9A4D00")

        for item in preview:
            tag = item["status"].lower()
            table.insert(
                "", "end",
                values=(
                    item["current_name"],
                    item["original_name"],
                    item.get("batch_id", batch_id or "all"),
                    item["status"],
                    item["detail"],
                ),
                tags=(tag,)
            )

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        button_frame = ttk.Frame(preview_window, padding=(12, 0, 12, 12))
        button_frame.grid(row=2, column=0, sticky="ew")
        button_frame.columnconfigure(0, weight=1)

        def close_preview():
            preview_window.grab_release()
            preview_window.destroy()

        def confirm_undo():
            if self.confirmation_open:
                return

            self.confirmation_open = True
            try:
                confirmed = messagebox.askyesno(
                    f"Confirm {scope_name} Undo",
                    f"Restore {scope_name.lower()} ({len(preview)} record(s))?\n\n"
                    "Only rows marked Ready will be renamed. Blocked rows remain "
                    "in the undo log for later review.",
                    icon="warning",
                    parent=preview_window
                )
            finally:
                self.confirmation_open = False

            if not confirmed:
                return

            close_preview()
            self.operation_in_progress = True
            try:
                undone_count, failed_count, message = self.operations.undo_batch(
                    batch_id,
                    self.log
                )
                if message:
                    self.log(message)
                    messagebox.showwarning("Undo Warning", message)
                else:
                    self.log(
                        f"{scope_name} undo complete: restored={undone_count}, "
                        f"blocked={failed_count}"
                    )
                    messagebox.showinfo(
                        "Undo Complete",
                        f"Restored: {undone_count}\nCould not restore: {failed_count}"
                    )
            except Exception as error:
                self.log(f"Unexpected undo error: {error}")
                messagebox.showerror("Undo Error", f"An unexpected error occurred:\n{error}")
            finally:
                self.operation_in_progress = False

            # Do not restart a full scan after an action performed on a
            # manually stopped partial scan.
            if self.folder_var.get().strip() and not self.scan_stopped_by_user:
                self.scan_files()
            else:
                self.refresh_table()

        ttk.Button(button_frame, text="Cancel", command=close_preview).grid(
            row=0, column=1, padx=(8, 0)
        )

        if not restore_all:
            def preview_all():
                all_preview, error_message = self.operations.preview_all_operations()
                if error_message:
                    messagebox.showerror("Undo Unavailable", error_message, parent=preview_window)
                    return
                close_preview()
                self.show_undo_preview(None, all_preview, restore_all=True)

            ttk.Button(
                button_frame,
                text="Preview All Recorded",
                command=preview_all
            ).grid(row=0, column=2, padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Restore All Recorded" if restore_all else "Restore Latest Batch",
            style="Danger.TButton",
            command=confirm_undo,
            state="normal" if ready_count else "disabled"
        ).grid(row=0, column=3 if not restore_all else 2, padx=(8, 0))

        preview_window.protocol("WM_DELETE_WINDOW", close_preview)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        scale_factor = ctypes.windll.shcore.GetScaleFactorForDevice(0)
    except Exception:
        scale_factor = 100

    root = tk.Tk()
    root.tk.call("tk", "scaling", scale_factor / 75)

    icon_file = get_resource_path("app.ico")
    root.iconbitmap(icon_file)
    ExtensionRepairApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
